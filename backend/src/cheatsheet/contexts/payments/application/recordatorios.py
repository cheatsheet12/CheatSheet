"""HS-T3 — despachar la cadena de recordatorios, y HU-E6-01 RN-03 — vencer lo que venció.

Dos barridos que comparten una idea: **el estado lo mueve un proceso, no una lectura.** Es lo
mismo que hace la DLQ del épico 4 y la reconciliación de D17, y acá se llama **D23**.

`VencerCobros` es el primero porque el segundo depende de él: la cadena cuenta días desde el
vencimiento, y un cobro que nadie marcó vencido es un cobro que nadie sabe que está en mora.

`DespacharRecordatorios` es el segundo, y su idempotencia es la **decisión D25**: pregunta
«cuál es el paso que falta», no «cuándo fue el último». La diferencia se nota cuando el
planificador se atrasa — un barrido por fechas manda los tres pasos de golpe, uno por paso
manda el que sigue.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from cheatsheet.contexts.payments.application.errors import RecordatorioDuplicado
from cheatsheet.contexts.payments.application.ports import (
    PasoDeCadena,
    PortCadenaDeEscalamiento,
    PortEnvioDeRecordatorio,
    PortRepositorioCobro,
    PortRepositorioRecordatorios,
)
from cheatsheet.contexts.payments.domain.cobro import Cobro
from cheatsheet.contexts.payments.domain.recordatorio import Recordatorio, proximo_paso
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.events import PublicadorDeEventos

logger = obtener_logger(__name__)


@dataclass(frozen=True, slots=True)
class ResultadoDeBarrido:
    """Cuántos se movieron. Lo que el worker registra y los tests afirman."""

    procesados: int
    #: Los que el barrido miró y decidió no tocar. Se cuenta a propósito: un barrido que
    #: procesa cero puede estar bien (nada vencía hoy) o puede estar roto, y la única forma de
    #: distinguirlo desde un log es saber cuántos evaluó.
    evaluados: int = 0


class VencerCobros:
    """HU-E6-01 RN-03 — pasa a `VENCIDO` lo que superó su vencimiento (decisión **D23**).

    Es una transición real y no una propiedad calculada, y las tres razones importan:

    1. **Los recordatorios dependen del estado.** HS-T3 RN-03 los detiene en `APROBADO` y
       `CANCELADO`; un estado que sólo existe al leerlo no dispara nada.
    2. **La bitácora tiene que registrarlo.** «Cuándo pasó a mora» es una pregunta que se hace
       en una discusión con un cliente.
    3. **El listado filtra por estado en la base** (RN-02). Un estado calculado en Python
       obliga a traer todo y filtrar en memoria, lo que se rompe con paginación.
    """

    def __init__(self, *, cobros: PortRepositorioCobro, publicador: PublicadorDeEventos) -> None:
        self._cobros = cobros
        self._publicador = publicador

    async def ejecutar(self, *, empresa_id: EmpresaId, ahora: datetime) -> ResultadoDeBarrido:
        candidatos = await self._cobros.abiertos_vencidos_a(ahora)
        vencidos = 0
        for cobro in candidatos:
            if cobro.estado is not cobro.estado.PENDIENTE:
                continue
            cobro.vencer(ahora)
            await self._cobros.guardar(cobro)
            vencidos += 1
            await self._publicador.publicar(
                EventoAuditable(
                    evento_id=uuid4(),
                    empresa_id=empresa_id,
                    ocurrido_en=ahora,
                    # Iniciador Sistema: esto lo hace el reloj, no una persona.
                    usuario_id=None,
                    modulo=Modulo.PAYMENTS,
                    accion="vencer_cobro",
                    entidad_afectada=f"Cobro:{cobro.id}",
                    resultado=Resultado.COMPLETADO,
                )
            )

        if vencidos:
            logger.info("cobros_vencidos", empresa_id=str(empresa_id), cantidad=vencidos)
        return ResultadoDeBarrido(procesados=vencidos, evaluados=len(candidatos))


class DespacharRecordatorios:
    """HS-T3 — manda el paso que corresponde de cada cadena abierta.

    **La idempotencia es el `paso`** (decisión **D25**), y se defiende en dos capas: el
    dominio calcula cuál falta, y el índice único `(cobro_id, paso)` rechaza el segundo
    despacho del mismo. La segunda existe porque dos barridos solapados pasan la primera.

    Un fallo de un cobro **no aborta el barrido**. Es el mismo criterio que el fan-out del
    épico 4: perder un recordatorio cuesta una corrida de espera; dejar que la excepción se
    escape cuesta todos los cobros que venían después en la lista.
    """

    def __init__(
        self,
        *,
        cobros: PortRepositorioCobro,
        recordatorios: PortRepositorioRecordatorios,
        envio: PortEnvioDeRecordatorio,
        cadena: PortCadenaDeEscalamiento,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._cobros = cobros
        self._recordatorios = recordatorios
        self._envio = envio
        self._cadena = cadena
        self._publicador = publicador

    async def ejecutar(self, *, empresa_id: EmpresaId, ahora: datetime) -> ResultadoDeBarrido:
        abiertos = await self._cobros.abiertos()
        if not abiertos:
            return ResultadoDeBarrido(procesados=0)

        cadena = await self._cadena.pasos(empresa_id=empresa_id)
        # Una sola consulta para todos: una por cobro serían N+1 sobre una tabla que crece con
        # cada recordatorio enviado.
        por_cobro = await self._recordatorios.de_cobros([cobro.id for cobro in abiertos])

        despachados = 0
        for cobro in abiertos:
            if await self._despachar_uno(
                empresa_id=empresa_id,
                cobro=cobro,
                previos=por_cobro.get(cobro.id, []),
                cadena=cadena,
                ahora=ahora,
            ):
                despachados += 1

        if despachados:
            logger.info(
                "recordatorios_despachados", empresa_id=str(empresa_id), cantidad=despachados
            )
        return ResultadoDeBarrido(procesados=despachados, evaluados=len(abiertos))

    async def _despachar_uno(
        self,
        *,
        empresa_id: EmpresaId,
        cobro: Cobro,
        previos: list[Recordatorio],
        cadena: tuple[PasoDeCadena, ...],
        ahora: datetime,
    ) -> bool:
        """Devuelve si mandó algo. Nunca levanta: un cobro roto no frena a los demás."""
        if not cobro.recibe_recordatorios:  # pragma: no cover - `abiertos` ya los filtra
            return False

        # Contando desde 1: `paso` es una columna que alguien va a leer en una consulta, y
        # «paso 0» no significa nada para quien la mire.
        numero = proximo_paso(previos)
        paso = cadena[numero - 1] if 1 <= numero <= len(cadena) else None
        if paso is None:
            # La cadena se terminó. No es un error: hay un tope de pasos a propósito, y una
            # deuda que sigue impaga después del último recordatorio es un problema humano.
            return False

        # **El día cero es el vencimiento**, no la creación del cobro. Es lo que hace legible
        # una cadena de «a los 3, a los 7, a los 15» y lo que la historia describe.
        if (ahora - cobro.vence_el).days < paso.dias:
            return False

        recordatorio = Recordatorio(id=uuid4(), cobro_id=cobro.id, paso=numero, canal=paso.canal)
        try:
            await self._recordatorios.agregar(recordatorio)
        except RecordatorioDuplicado:
            # Otro barrido llegó primero. **No es un error**: significa «esto ya salió», que
            # es exactamente lo que RN-05 pide garantizar.
            logger.info("recordatorio_ya_despachado", cobro_id=str(cobro.id), paso=numero)
            return False

        estado = await self._envio.enviar(
            empresa_id=empresa_id, cobro=cobro, canal=paso.canal, paso=numero
        )
        recordatorio.marcar_enviado(ahora)
        recordatorio.marcar_entrega(estado)
        await self._recordatorios.guardar(recordatorio)

        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                usuario_id=None,
                modulo=Modulo.PAYMENTS,
                accion="enviar_recordatorio",
                entidad_afectada=f"Cobro:{cobro.id}",
                resultado=Resultado.COMPLETADO,
            )
        )
        return True


class VerRecordatorios:
    """HU-E6-02 RN-01 — el historial que muestra PAN-COB-02."""

    def __init__(self, recordatorios: PortRepositorioRecordatorios) -> None:
        self._recordatorios = recordatorios

    async def ejecutar(self, cobro_id: UUID) -> list[Recordatorio]:
        return await self._recordatorios.de_cobro(cobro_id)


__all__ = [
    "DespacharRecordatorios",
    "ResultadoDeBarrido",
    "VencerCobros",
    "VerRecordatorios",
]
