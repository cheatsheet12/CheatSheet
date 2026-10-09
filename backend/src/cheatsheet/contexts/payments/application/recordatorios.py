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

from cheatsheet.contexts.payments.application.errors import (
    DespachoNoPersistido,
    RecordatorioDuplicado,
)
from cheatsheet.contexts.payments.application.ports import (
    PortRepositorioCobro,
    PortRepositorioRecordatorios,
)
from cheatsheet.contexts.payments.application.ports_de_recordatorios import (
    PasoDeCadena,
    PortCadenaDeEscalamiento,
    PortEnvioDeRecordatorio,
    ResultadoDeEnvio,
)
from cheatsheet.contexts.payments.application.ports_envio import PortAislamiento
from cheatsheet.contexts.payments.domain.cobro import Cobro
from cheatsheet.contexts.payments.domain.recordatorio import (
    EstadoEntrega,
    Recordatorio,
    proximo_paso,
)
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
    #: Recordatorios cuyo envío terminó `FALLIDO`. Quedan registrados (con fecha, para que el
    #: índice único no los reenvíe) pero **no** cuentan como `procesados`: un barrido que
    #: «despachó» lo que nunca salió esconde justo el incidente que hay que mirar.
    fallidos: int = 0


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

    **Un fallo de un cobro no aborta el barrido ni deshace a los demás** (U5, H1). El barrido
    corre en una sola transacción por empresa, y si la excepción de un cobro la volteara, las
    filas de los cobros anteriores —cuyos mensajes ya salieron— se perderían y la hora siguiente
    los mandaría de nuevo. Por eso:

    - cada cobro corre en su propio **savepoint** (`aislamiento`): si la base rechaza algo,
      sólo se deshacen las filas de ese cobro;
    - el envío va protegido: si el adaptador levanta (el contrato dice que no debe), el paso
      queda registrado `FALLIDO` con fecha, y el índice único no lo deja salir de nuevo.

    Un único caso residual de reenvío: si la base falla **después** de que el mensaje salió y
    **antes** de liberar el savepoint de ese cobro, sus filas se deshacen y ese cobro (sólo ése)
    se reenvía en el barrido siguiente.
    """

    def __init__(
        self,
        *,
        cobros: PortRepositorioCobro,
        recordatorios: PortRepositorioRecordatorios,
        envio: PortEnvioDeRecordatorio,
        cadena: PortCadenaDeEscalamiento,
        publicador: PublicadorDeEventos,
        aislamiento: PortAislamiento,
    ) -> None:
        self._cobros = cobros
        self._recordatorios = recordatorios
        self._envio = envio
        self._cadena = cadena
        self._publicador = publicador
        self._aislamiento = aislamiento

    async def ejecutar(self, *, empresa_id: EmpresaId, ahora: datetime) -> ResultadoDeBarrido:
        abiertos = await self._cobros.abiertos()
        if not abiertos:
            return ResultadoDeBarrido(procesados=0)

        cadena = await self._cadena.pasos(empresa_id=empresa_id)
        # Una sola consulta para todos: una por cobro serían N+1 sobre una tabla que crece con
        # cada recordatorio enviado.
        por_cobro = await self._recordatorios.de_cobros([cobro.id for cobro in abiertos])

        despachados = 0
        fallidos = 0
        for cobro in abiertos:
            try:
                async with self._aislamiento.aislar():
                    salio = await self._despachar_uno(
                        empresa_id=empresa_id,
                        cobro=cobro,
                        previos=por_cobro.get(cobro.id, []),
                        cadena=cadena,
                        ahora=ahora,
                    )
            except DespachoNoPersistido:
                # Sin datos del cliente ni del error: sólo qué cobro. Se deshizo lo de este
                # cobro; los anteriores siguen confirmados y el barrido sigue.
                logger.warning("recordatorio_no_persistido", cobro_id=str(cobro.id))
                continue
            if salio is EstadoEntrega.FALLIDO:
                fallidos += 1
            elif salio is not None:
                despachados += 1

        if despachados or fallidos:
            logger.info(
                "recordatorios_despachados",
                empresa_id=str(empresa_id),
                cantidad=despachados,
                fallidos=fallidos,
            )
        return ResultadoDeBarrido(
            procesados=despachados, evaluados=len(abiertos), fallidos=fallidos
        )

    async def _despachar_uno(
        self,
        *,
        empresa_id: EmpresaId,
        cobro: Cobro,
        previos: list[Recordatorio],
        cadena: tuple[PasoDeCadena, ...],
        ahora: datetime,
    ) -> EstadoEntrega | None:
        """Devuelve cómo terminó el envío, o `None` si no intentó ninguno.

        Nunca levanta: un cobro roto no frena a los demás.
        """
        if not cobro.recibe_recordatorios:  # pragma: no cover - `abiertos` ya los filtra
            return None

        # Contando desde 1: `paso` es una columna que alguien va a leer en una consulta, y
        # «paso 0» no significa nada para quien la mire.
        numero = proximo_paso(previos)
        paso = cadena[numero - 1] if 1 <= numero <= len(cadena) else None
        if paso is None:
            # La cadena se terminó. No es un error: hay un tope de pasos a propósito, y una
            # deuda que sigue impaga después del último recordatorio es un problema humano.
            return None

        # **El día cero es el vencimiento**, no la creación del cobro. Es lo que hace legible
        # una cadena de «a los 3, a los 7, a los 15» y lo que la historia describe.
        if (ahora - cobro.vence_el).days < paso.dias:
            return None

        recordatorio = Recordatorio(id=uuid4(), cobro_id=cobro.id, paso=numero, canal=paso.canal)
        try:
            await self._recordatorios.agregar(recordatorio)
        except RecordatorioDuplicado:
            # Otro barrido llegó primero. **No es un error**: significa «esto ya salió», que
            # es exactamente lo que RN-05 pide garantizar.
            logger.info("recordatorio_ya_despachado", cobro_id=str(cobro.id), paso=numero)
            return None

        try:
            resultado = await self._envio.enviar(
                empresa_id=empresa_id, cobro=cobro, canal=paso.canal, paso=numero
            )
        except Exception as exc:  # noqa: BLE001 — ver abajo
            # `Exception` es lo que `CLAUDE.md` §5 prohíbe en general, y acá está acotado por el
            # motivo: el puerto lo implementan adaptadores que podrían levantar cualquier cosa,
            # y su contrato dice que no deben. Es defensa en profundidad (igual que
            # `SalidaAlCliente`): el paso queda `FALLIDO` con fecha y el índice `(cobro_id,
            # paso)` no lo deja salir otra vez. Sólo la clase de la excepción, nunca su texto.
            logger.warning(
                "recordatorio_envio_fallido",
                cobro_id=str(cobro.id),
                paso=numero,
                causa=type(exc).__name__,
            )
            resultado = ResultadoDeEnvio(estado=EstadoEntrega.FALLIDO, codigo="ERROR")
        estado = resultado.estado
        recordatorio.marcar_enviado(ahora, externo_id=resultado.externo_id)
        recordatorio.marcar_entrega(estado, motivo=resultado.codigo)
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
                # El envío fallido igual deja la fila (el índice único la necesita), pero la
                # bitácora no puede decir que salió.
                resultado=(
                    Resultado.ERROR if estado is EstadoEntrega.FALLIDO else Resultado.COMPLETADO
                ),
            )
        )
        return estado


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
