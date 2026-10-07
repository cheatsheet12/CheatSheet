"""El envío de un recordatorio, en tres tiempos, y su reintento acotado (U7, tramo ii, D-U7-3).

**Por qué tres tiempos.** El barrido corre en la unidad de trabajo de la empresa, que confirma recién
al final. Si insertaba la fila, llamaba a Meta y guardaba el resultado todo ahí adentro, un callback
`failed` o `delivered` que llegara antes del commit no encontraba la fila y se perdía (H1,
`TODO.md` §22.57), y la llamada a Meta corría con la transacción abierta (G5, ADR-0014). Ahora:

1. **Reservar** (transacción corta): se escribe la fila con el intento ya contado
   (`intentos = n`, `proximo_intento_en = ahora + VENTANA_DE_ENVIO`) y se **confirma**.
2. **Mandar**: la llamada a Meta, con nada sin confirmar.
3. **Registrar** (otra transacción corta): el resultado —`wamid`, estado, error— y se confirma.

**Ventanas de caída y cómo se resuelve cada una.** La fila nunca se vuelve a mandar si un envío pudo
haber salido: un duplicado de un recordatorio es peor que uno que falta (ADR-0011 punto 6).

- Cae **antes** de reservar o falla el commit de la reserva: no hay fila y nada pudo salir. La hora
  siguiente lo evalúa como un paso nuevo.
- Cae **después de reservar y antes de llamar a Meta**: la fila queda «en curso» con su ventana. No se
  puede distinguir de la siguiente, así que se trata igual.
- Cae **después de que Meta aceptó y antes de registrar** (o falla el commit del resultado): ídem.
  Vencida la ventana, el siguiente barrido la resuelve `FALLIDO` con motivo `INCIERTO` y **no la
  reenvía**, que es lo mismo que el canal hace con un timeout de lectura (`EnvioIncierto`).
- Una fila **sin intentar** (`intentos = 0`: ningún envío empezó, nada pudo salir) sí se manda; es lo
  que desata una cadena trabada por una fila sin `enviado_en` (caso 4).

**Reintento.** Solo una falla marcada **transitoria** (`ResultadoDeEnvio.transitoria`) vuelve a
intentarse, sobre la **misma fila** (un `UPDATE`, nunca un `INSERT`: la idempotencia de RN-05 es el
índice `(cobro_id, paso)`), hasta `REINTENTOS_MAXIMOS` intentos con espera de 1 h, 2 h. Un rechazo
permanente, un resultado incierto o un `failed` por callback no se reintentan.

**Atomicidad por ítem.** Cada reserva y cada registro corren en su propio savepoint
(`PortAislamiento`) y se confirman con `PortTransaccion`: lo que la base rechaza deshace solo ese
ítem.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
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
    PortEnvioDeRecordatorio,
    ResultadoDeEnvio,
)
from cheatsheet.contexts.payments.application.ports_envio import PortAislamiento, PortTransaccion
from cheatsheet.contexts.payments.domain.cobro import Cobro
from cheatsheet.contexts.payments.domain.recordatorio import (
    INCIERTO,
    EstadoEntrega,
    Recordatorio,
)
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.events import PublicadorDeEventos

logger = obtener_logger(__name__)


class Desenlace(StrEnum):
    """Cómo terminó el trato con una fila, para los contadores del barrido."""

    SALIO = "SALIO"
    FALLO = "FALLO"
    EN_REINTENTO = "EN_REINTENTO"
    #: No se mandó nada ni se cambió el resultado (otro barrido la tenía, o se descartó).
    NADA = "NADA"
    #: Meta pudo haberlo recibido y la base no guardó el resultado: queda «en curso».
    SIN_REGISTRAR = "SIN_REGISTRAR"


class EnvioConReintento:
    """Reserva, manda y registra un recordatorio; y retoma los que esperan (U7, D-U7-3)."""

    def __init__(
        self,
        *,
        cobros: PortRepositorioCobro,
        recordatorios: PortRepositorioRecordatorios,
        envio: PortEnvioDeRecordatorio,
        publicador: PublicadorDeEventos,
        aislamiento: PortAislamiento,
        transaccion: PortTransaccion,
    ) -> None:
        self._cobros = cobros
        self._recordatorios = recordatorios
        self._envio = envio
        self._publicador = publicador
        self._aislamiento = aislamiento
        self._transaccion = transaccion

    # ------------------------------------------------------------------ paso nuevo

    async def enviar_nuevo(
        self, *, empresa_id: EmpresaId, cobro: Cobro, canal: str, numero: int, ahora: datetime
    ) -> Desenlace:
        """El primer intento de un paso que todavía no tiene fila."""
        recordatorio = Recordatorio(id=uuid4(), cobro_id=cobro.id, paso=numero, canal=canal)
        recordatorio.iniciar_intento(ahora)
        try:
            async with self._aislamiento.aislar():
                await self._recordatorios.agregar(recordatorio)
            await self._transaccion.confirmar()
        except RecordatorioDuplicado:
            # Otro barrido llegó primero. **No es un error**: significa «esto ya salió», que es
            # exactamente lo que RN-05 pide garantizar.
            logger.info("recordatorio_ya_despachado", cobro_id=str(cobro.id), paso=numero)
            return Desenlace.NADA
        except DespachoNoPersistido:
            # Sin la fila confirmada no hay E/S: nada pudo salir. Sin datos del cliente ni del error.
            logger.warning("recordatorio_no_persistido", cobro_id=str(cobro.id))
            return Desenlace.NADA
        return await self._mandar_y_registrar(empresa_id, cobro, recordatorio, ahora)

    # ------------------------------------------------------------------ fila existente

    async def retomar(
        self, *, empresa_id: EmpresaId, recordatorio_id: UUID, ahora: datetime
    ) -> Desenlace:
        """Toma una fila ya existente que le toca a este barrido: sin intentar o con su fecha.

        La relee **bloqueada**: si otro barrido la tomó mientras tanto, ya no le toca y se deja.
        """
        try:
            async with self._aislamiento.aislar():
                tomada = await self._tomar(empresa_id, recordatorio_id, ahora)
            await self._transaccion.confirmar()
        except DespachoNoPersistido:
            logger.warning("recordatorio_no_persistido", recordatorio_id=str(recordatorio_id))
            return Desenlace.NADA
        if isinstance(tomada, Desenlace):
            return tomada
        recordatorio, cobro = tomada
        return await self._mandar_y_registrar(empresa_id, cobro, recordatorio, ahora)

    async def reintentar_pendientes(
        self, *, empresa_id: EmpresaId, ahora: datetime
    ) -> list[Desenlace]:
        """Las filas que esperan un reintento o cuyo envío en curso venció, con su fecha cumplida."""
        desenlaces: list[Desenlace] = []
        for pendiente in await self._recordatorios.pendientes_de_reintento(ahora):
            desenlaces.append(
                await self.retomar(empresa_id=empresa_id, recordatorio_id=pendiente.id, ahora=ahora)
            )
        return desenlaces

    async def _tomar(
        self, empresa_id: EmpresaId, recordatorio_id: UUID, ahora: datetime
    ) -> tuple[Recordatorio, Cobro] | Desenlace:
        """Decide qué hacer con la fila bloqueada. Devuelve el intento a mandar, o cómo terminó."""
        recordatorio = await self._recordatorios.buscar_para_actualizar(recordatorio_id)
        if recordatorio is None or not recordatorio.corresponde_intentar(ahora):
            return Desenlace.NADA
        if recordatorio.envio_perdido(ahora):
            # Un envío empezó y nunca registró su resultado: Meta pudo haberlo aceptado.
            recordatorio.fallar(ahora, INCIERTO)
            await self._recordatorios.guardar(recordatorio)
            await self._publicar(empresa_id, recordatorio.cobro_id, ahora, Resultado.ERROR)
            logger.warning(
                "recordatorio_envio_perdido",
                cobro_id=str(recordatorio.cobro_id),
                paso=recordatorio.paso,
            )
            return Desenlace.FALLO
        cobro = await self._cobros.buscar_por_id(recordatorio.cobro_id)
        if cobro is None or not cobro.recibe_recordatorios:
            recordatorio.descartar()
            await self._recordatorios.guardar(recordatorio)
            return Desenlace.NADA
        recordatorio.iniciar_intento(ahora)
        await self._recordatorios.guardar(recordatorio)
        return recordatorio, cobro

    # ------------------------------------------------------------------ mandar y registrar

    async def _mandar_y_registrar(
        self, empresa_id: EmpresaId, cobro: Cobro, recordatorio: Recordatorio, ahora: datetime
    ) -> Desenlace:
        # **Sin nada sin confirmar**: la reserva ya se confirmó (`PortTransaccion`).
        resultado = await self._mandar(empresa_id, cobro, recordatorio)
        try:
            async with self._aislamiento.aislar():
                desenlace = await self._registrar(empresa_id, recordatorio, resultado, ahora)
            await self._transaccion.confirmar()
        except DespachoNoPersistido:
            # La fila sigue «en curso» y se resolverá `INCIERTO` al vencer su ventana: no se manda
            # otra vez lo que pudo haber salido. Sin datos del cliente ni del error.
            logger.warning(
                "recordatorio_resultado_no_persistido",
                cobro_id=str(cobro.id),
                paso=recordatorio.paso,
            )
            return Desenlace.SIN_REGISTRAR
        return desenlace

    async def _mandar(
        self, empresa_id: EmpresaId, cobro: Cobro, recordatorio: Recordatorio
    ) -> ResultadoDeEnvio:
        try:
            return await self._envio.enviar(
                empresa_id=empresa_id,
                cobro=cobro,
                canal=recordatorio.canal,
                paso=recordatorio.paso,
            )
        except Exception as exc:  # noqa: BLE001 — ver abajo
            # `Exception` es lo que `CLAUDE.md` §5 prohíbe en general, y acá está acotado por el
            # motivo: el puerto lo implementan adaptadores que podrían levantar cualquier cosa, y
            # su contrato dice que no deben. Es defensa en profundidad: el paso queda `FALLIDO` y,
            # al no ser transitorio, no se reintenta. Sólo la clase de la excepción, nunca su texto.
            logger.warning(
                "recordatorio_envio_fallido",
                cobro_id=str(cobro.id),
                paso=recordatorio.paso,
                causa=type(exc).__name__,
            )
            return ResultadoDeEnvio(estado=EstadoEntrega.FALLIDO, codigo="ERROR")

    async def _registrar(
        self,
        empresa_id: EmpresaId,
        recordatorio: Recordatorio,
        resultado: ResultadoDeEnvio,
        ahora: datetime,
    ) -> Desenlace:
        if resultado.estado is EstadoEntrega.FALLIDO:
            hay_reintento = recordatorio.registrar_falla(
                ahora, codigo=resultado.codigo or "ERROR", transitoria=resultado.transitoria
            )
            await self._recordatorios.guardar(recordatorio)
            if hay_reintento:
                logger.info(
                    "recordatorio_reintento_programado",
                    cobro_id=str(recordatorio.cobro_id),
                    paso=recordatorio.paso,
                    intentos=recordatorio.intentos,
                )
                return Desenlace.EN_REINTENTO
            await self._publicar(empresa_id, recordatorio.cobro_id, ahora, Resultado.ERROR)
            return Desenlace.FALLO
        recordatorio.marcar_enviado(ahora, externo_id=resultado.externo_id)
        recordatorio.marcar_entrega(resultado.estado, motivo=resultado.codigo)
        await self._recordatorios.guardar(recordatorio)
        await self._publicar(empresa_id, recordatorio.cobro_id, ahora, Resultado.COMPLETADO)
        return Desenlace.SALIO

    async def _publicar(
        self, empresa_id: EmpresaId, cobro_id: UUID, ahora: datetime, resultado: Resultado
    ) -> None:
        """`enviar_recordatorio`: **una vez por recordatorio**, al terminar. Un intento
        intermedio que espera su reintento no es una falla de la bitácora, y un envío fallido
        no puede decir que salió."""
        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                usuario_id=None,
                modulo=Modulo.PAYMENTS,
                accion="enviar_recordatorio",
                entidad_afectada=f"Cobro:{cobro_id}",
                resultado=resultado,
            )
        )


__all__ = ["Desenlace", "EnvioConReintento"]
