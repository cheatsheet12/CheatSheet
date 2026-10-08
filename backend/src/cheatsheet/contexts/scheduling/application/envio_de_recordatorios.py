"""El envío de un recordatorio de turno, en tres tiempos, y su reintento acotado (U8, D-U8-8, D-U8-10).

Es la misma pieza que `payments/application/reintentos.py` (U7), con un turno en lugar de un cobro.
El barrido corre en la unidad de trabajo de la empresa, que confirma recién al final; si insertaba la
fila, llamaba a Meta y guardaba el resultado ahí adentro, un callback `failed` o `delivered` que
llegara antes del commit no encontraba el mensaje y se perdía, y la llamada a Meta corría con
escrituras sin confirmar (G5). Ahora:

1. **Reservar** (transacción corta): se **prepara** el mensaje (lee contacto, servicio y plantilla) y
   se escribe la fila con el intento ya contado y la ventana abierta, todo en un savepoint, y se
   **confirma**. Si preparar falla en la base, no queda fila y el barrido siguiente lo evalúa de nuevo.
2. **Mandar**: se relee el turno (si se canceló o se movió mientras tanto, se descarta sin mandar) y se
   llama al canal. **Sin escrituras sin confirmar ni locks**: la transacción abierta es la vacía que
   deja `confirmar()` al volver a declarar la empresa (N1 de U7). `NotificarAlCliente` guarda el
   mensaje `SISTEMA` **después** de la respuesta de Meta, en su savepoint.
3. **Registrar** (otra transacción corta): el resultado y la bitácora, y se confirma. Esa confirmación
   es la que hace visible el mensaje `SISTEMA` para los callbacks.

**El reloj.** El `ahora` del barrido solo decide *qué* le toca a la corrida. Toda fecha que se
**escribe** (la ventana de la reserva, la espera del reintento, el evento) sale del reloj real en ese
momento (S2 de U7).

**Ventanas de caída.** Un recordatorio duplicado es peor que uno que falta: si el proceso muere entre
reservar y registrar, la fila queda «en curso» con su ventana y, vencida, el barrido siguiente la
resuelve `FALLIDO` con motivo `INCIERTO` **sin reenviarla**. Cae antes de reservar: no hay fila y nada
pudo salir.

**Reintento.** Solo una falla marcada transitoria se vuelve a intentar, sobre la **misma fila** (un
`UPDATE`, nunca un `INSERT`), hasta tres intentos con esperas de 15 y 30 minutos y nunca después de la
hora del turno. La fila se retoma **bloqueada** (`buscar_para_actualizar`): dos barridos solapados no
retoman el mismo reintento.

Ningún log lleva el nombre, el teléfono ni el texto; solo ids, la anticipación y la clase del error.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from enum import StrEnum
from typing import TypeVar
from uuid import UUID, uuid4

from cheatsheet.contexts.scheduling.application.errors import RecordatorioDeTurnoDuplicado
from cheatsheet.contexts.scheduling.application.ports_de_recordatorios import (
    PortEnvioDeRecordatorioDeTurno,
    PortRepositorioRecordatoriosDeTurno,
    PortTurnosPorRecordar,
    RecordatorioListo,
    ResultadoDelEnvio,
    SinTelefono,
)
from cheatsheet.contexts.scheduling.domain.recordatorio_de_turno import (
    AGENDA_APAGADA,
    ANTICIPACION_SUPERADA,
    FRANJA_CAMBIADA,
    INCIERTO,
    SIN_TELEFONO,
    TURNO_CERRADO,
    TURNO_EMPEZADO,
    RecordatorioDeTurno,
    ResultadoDeRecordatorio,
)
from cheatsheet.contexts.scheduling.domain.turno import Turno
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.clock import Reloj
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.transaccion import DespachoNoPersistido, PortAislamiento, PortTransaccion

logger = obtener_logger(__name__)

_T = TypeVar("_T")

#: Lo que escribe la bitácora: `usuario_id=None` dice que actuó el sistema (el barrido).
ACCION_DE_BITACORA = "enviar_recordatorio_de_turno"


class Desenlace(StrEnum):
    """Cómo terminó el trato con una fila o un turno, para los contadores del barrido."""

    SALIO = "SALIO"
    FALLO = "FALLO"
    EN_REINTENTO = "EN_REINTENTO"
    OMITIDO = "OMITIDO"
    DESCARTADO = "DESCARTADO"
    #: No se mandó nada ni se cambió el resultado (otro barrido la tenía, o nada la hacía caber).
    NADA = "NADA"
    #: No se pudo registrar lo que pasó: la fila queda «en curso» y se resolverá `INCIERTO` al vencer
    #: su ventana. Nunca se reenvía.
    SIN_REGISTRAR = "SIN_REGISTRAR"


class EnvioDeRecordatorios:
    """Reserva, manda y registra un recordatorio de turno; y retoma los que esperan."""

    def __init__(
        self,
        *,
        turnos: PortTurnosPorRecordar,
        recordatorios: PortRepositorioRecordatoriosDeTurno,
        envio: PortEnvioDeRecordatorioDeTurno,
        publicador: PublicadorDeEventos,
        aislamiento: PortAislamiento,
        transaccion: PortTransaccion,
        reloj: Reloj,
    ) -> None:
        self._turnos = turnos
        self._recordatorios = recordatorios
        self._envio = envio
        self._publicador = publicador
        self._aislamiento = aislamiento
        self._transaccion = transaccion
        self._reloj = reloj

    # ------------------------------------------------------------------ fila nueva

    async def enviar_nuevo(self, *, turno: Turno, anticipacion_min: int) -> Desenlace:
        """El primer intento de una anticipación que todavía no tiene fila."""
        recordatorio = RecordatorioDeTurno.para(
            id=uuid4(), turno=turno, anticipacion_min=anticipacion_min, ahora=self._reloj.ahora()
        )

        async def reservar() -> RecordatorioListo | Desenlace:
            # Primero se lee (preparar), después se escribe: si la lectura falla, no hay fila.
            preparado = await self._envio.preparar(turno, anticipacion_min)
            ahora = self._reloj.ahora()
            if isinstance(preparado, SinTelefono):
                recordatorio.omitir(ahora, SIN_TELEFONO)
                await self._recordatorios.agregar(recordatorio)
                return Desenlace.OMITIDO
            recordatorio.iniciar_intento(ahora)
            await self._recordatorios.agregar(recordatorio)
            return preparado

        reservado = await self._reservado(
            reservar, turno_id=str(turno.id), anticipacion_min=anticipacion_min
        )
        if isinstance(reservado, Desenlace):
            return reservado
        return await self._mandar_y_registrar(recordatorio, reservado)

    async def omitir_superada(self, *, turno: Turno, anticipacion_min: int) -> Desenlace:
        """Deja la fila de una anticipación vieja ya resuelta: `OMITIDO` por `ANTICIPACION_SUPERADA`.

        La fila ocupa la clave única, así que ningún barrido la manda después.
        """
        ahora = self._reloj.ahora()
        recordatorio = RecordatorioDeTurno.para(
            id=uuid4(), turno=turno, anticipacion_min=anticipacion_min, ahora=ahora
        )
        recordatorio.omitir(ahora, ANTICIPACION_SUPERADA)

        async def guardar() -> Desenlace:
            await self._recordatorios.agregar(recordatorio)
            return Desenlace.OMITIDO

        return await self._reservado(
            guardar, turno_id=str(turno.id), anticipacion_min=anticipacion_min
        )

    # ------------------------------------------------------------------ fila existente

    async def retomar(
        self, *, recordatorio_id: UUID, ahora: datetime, agenda_apagada: bool = False
    ) -> Desenlace:
        """Toma una fila ya existente que le toca a este barrido: su ventana venció o su espera se cumplió.

        La relee **bloqueada**: si otro barrido la tomó mientras tanto, ya no le toca y se deja.
        `ahora` solo decide si le toca; lo que se escribe sale del reloj real. Con la agenda apagada
        no se reintenta nada: la fila se descarta.
        """
        tomada = await self._reservado(
            lambda: self._tomar(recordatorio_id, ahora, agenda_apagada),
            recordatorio_id=str(recordatorio_id),
        )
        if isinstance(tomada, Desenlace):
            return tomada
        recordatorio, preparado = tomada
        return await self._mandar_y_registrar(recordatorio, preparado)

    async def _reservado(
        self, bloque: Callable[[], Awaitable[_T]], **datos: str | int
    ) -> _T | Desenlace:
        """Corre `bloque` en un savepoint y lo confirma. Si no se pudo, `Desenlace.NADA`.

        Nada de lo que falle acá deja una fila a medias: el savepoint se deshace entero.
        """
        try:
            async with self._aislamiento.aislar():
                resultado = await bloque()
        except RecordatorioDeTurnoDuplicado:
            # Otro barrido llegó primero. **No es un error**: significa «esto ya se atendió», que
            # es exactamente lo que la clave única garantiza.
            logger.info("recordatorio_de_turno_ya_despachado", **datos)
            return Desenlace.NADA
        except DespachoNoPersistido:
            # Sin la fila confirmada no hay E/S: nada pudo salir. Sin datos del cliente ni del error.
            logger.warning("recordatorio_de_turno_no_persistido", **datos)
            return Desenlace.NADA
        except Exception as exc:  # noqa: BLE001 — ver abajo
            # Un adaptador que rompe el contrato de `preparar` (solo puede levantar lo que la base
            # rechaza). El savepoint ya se deshizo: no hay fila y el resto del barrido sigue.
            logger.warning("recordatorio_de_turno_no_preparado", **datos, causa=type(exc).__name__)
            return Desenlace.NADA
        try:
            await self._transaccion.confirmar()
        except DespachoNoPersistido:
            logger.warning("recordatorio_de_turno_no_persistido", **datos)
            return Desenlace.NADA
        return resultado

    async def _tomar(
        self, recordatorio_id: UUID, ahora: datetime, agenda_apagada: bool
    ) -> tuple[RecordatorioDeTurno, RecordatorioListo] | Desenlace:
        """Decide qué hacer con la fila bloqueada. Devuelve el intento a mandar, o cómo terminó."""
        recordatorio = await self._recordatorios.buscar_para_actualizar(recordatorio_id)
        if recordatorio is None or recordatorio.terminado:
            return Desenlace.NADA
        real = self._reloj.ahora()
        if recordatorio.envio_perdido(ahora):
            # Un envío empezó y nunca registró su resultado: Meta pudo haberlo aceptado.
            recordatorio.fallar(real, INCIERTO)
            await self._recordatorios.guardar(recordatorio)
            await self._publicar(recordatorio, real, Resultado.ERROR)
            logger.warning(
                "recordatorio_de_turno_envio_perdido",
                turno_id=str(recordatorio.turno_id),
                anticipacion_min=recordatorio.anticipacion_min,
            )
            return Desenlace.FALLO
        if not recordatorio.reintento_vencido(ahora):
            return Desenlace.NADA
        if agenda_apagada:
            recordatorio.descartar(real, AGENDA_APAGADA)
            await self._recordatorios.guardar(recordatorio)
            return Desenlace.DESCARTADO
        turno = await self._turnos.releer(recordatorio.turno_id)
        motivo = _motivo_de_descarte(turno, recordatorio, real)
        if turno is None or motivo is not None:
            recordatorio.descartar(real, motivo or TURNO_CERRADO)
            await self._recordatorios.guardar(recordatorio)
            return Desenlace.DESCARTADO
        # Se prepara **antes** de escribir: si la lectura falla, la fila queda como estaba y el
        # barrido siguiente la retoma.
        preparado = await self._envio.preparar(turno, recordatorio.anticipacion_min)
        if isinstance(preparado, SinTelefono):
            recordatorio.omitir(real, SIN_TELEFONO)
            await self._recordatorios.guardar(recordatorio)
            return Desenlace.OMITIDO
        recordatorio.iniciar_intento(self._reloj.ahora())
        await self._recordatorios.guardar(recordatorio)
        return recordatorio, preparado

    # ------------------------------------------------------------------ mandar y registrar

    async def _mandar_y_registrar(
        self, recordatorio: RecordatorioDeTurno, preparado: RecordatorioListo
    ) -> Desenlace:
        cerrado = await self._turno_cambio_entretanto(recordatorio)
        if cerrado is not None:
            return cerrado
        # **Sin escrituras sin confirmar ni locks**: la reserva ya se confirmó (`PortTransaccion`) y
        # el mensaje ya está armado.
        resultado = await self._mandar(preparado)
        try:
            async with self._aislamiento.aislar():
                desenlace = await self._registrar(recordatorio, resultado)
            await self._transaccion.confirmar()
        except DespachoNoPersistido:
            # La fila sigue «en curso» y se resolverá `INCIERTO` al vencer su ventana: no se manda
            # otra vez lo que pudo haber salido.
            logger.warning(
                "recordatorio_de_turno_resultado_no_persistido",
                turno_id=str(recordatorio.turno_id),
                anticipacion_min=recordatorio.anticipacion_min,
            )
            return Desenlace.SIN_REGISTRAR
        return desenlace

    async def _turno_cambio_entretanto(self, recordatorio: RecordatorioDeTurno) -> Desenlace | None:
        """Después de reservar, vuelve a leer el turno; si se canceló o se movió, no se manda.

        Devuelve `None` si el turno sigue como estaba. Si no, la fila se descarta y devuelve cómo
        terminó. Si la lectura falla en la base, **no se manda** y la fila queda «en curso» (se
        resolverá `INCIERTO` sin haber salido nada: seguro, un falso `FALLIDO`, nunca un duplicado).
        """
        try:
            async with self._aislamiento.aislar():
                turno = await self._turnos.releer(recordatorio.turno_id)
                real = self._reloj.ahora()
                motivo = _motivo_de_descarte(turno, recordatorio, real)
                if turno is not None and motivo is None:
                    return None
                recordatorio.descartar(real, motivo or TURNO_CERRADO)
                await self._recordatorios.guardar(recordatorio)
            await self._transaccion.confirmar()
        except DespachoNoPersistido:
            logger.warning(
                "recordatorio_de_turno_no_revisado",
                turno_id=str(recordatorio.turno_id),
                anticipacion_min=recordatorio.anticipacion_min,
            )
            return Desenlace.SIN_REGISTRAR
        return Desenlace.DESCARTADO

    async def _mandar(self, listo: RecordatorioListo) -> ResultadoDelEnvio:
        try:
            return await self._envio.mandar(listo)
        except Exception as exc:  # noqa: BLE001 — ver abajo
            # El puerto lo implementan adaptadores que podrían levantar cualquier cosa, y su contrato
            # dice que no deben. Defensa en profundidad: queda `FALLIDO` y, al no ser transitoria,
            # no se reintenta. Solo la clase de la excepción, nunca su texto.
            logger.warning(
                "recordatorio_de_turno_envio_fallido",
                turno_id=str(listo.turno_id),
                anticipacion_min=listo.anticipacion_min,
                causa=type(exc).__name__,
            )
            return ResultadoDelEnvio(enviado=False, falla="ERROR")

    async def _registrar(
        self, recordatorio: RecordatorioDeTurno, resultado: ResultadoDelEnvio
    ) -> Desenlace:
        ahora = self._reloj.ahora()  # el de ahora, no el del inicio del barrido (S2)
        if resultado.enviado:
            recordatorio.marcar_enviado(ahora)
            await self._recordatorios.guardar(recordatorio)
            await self._publicar(recordatorio, ahora, Resultado.COMPLETADO)
            return Desenlace.SALIO
        hay_reintento = recordatorio.registrar_falla(
            ahora, codigo=resultado.falla or "ERROR", transitoria=resultado.transitoria
        )
        await self._recordatorios.guardar(recordatorio)
        if hay_reintento:
            logger.info(
                "recordatorio_de_turno_reintento_programado",
                turno_id=str(recordatorio.turno_id),
                anticipacion_min=recordatorio.anticipacion_min,
                intentos=recordatorio.intentos,
            )
            return Desenlace.EN_REINTENTO
        if recordatorio.resultado is ResultadoDeRecordatorio.DESCARTADO:
            # La espera del reintento caía después de la hora del turno: ya no tiene sentido.
            return Desenlace.DESCARTADO
        await self._publicar(recordatorio, ahora, Resultado.ERROR)
        return Desenlace.FALLO

    async def _publicar(
        self, recordatorio: RecordatorioDeTurno, ahora: datetime, resultado: Resultado
    ) -> None:
        """`enviar_recordatorio_de_turno`: **una vez por recordatorio**, al terminar.

        Un intento intermedio que espera su reintento no es una falla de la bitácora. Sin datos
        personales: el sistema actuó (`usuario_id=None`) y la entidad es el turno.
        """
        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=EmpresaId(recordatorio.empresa_id),
                ocurrido_en=ahora,
                usuario_id=None,
                modulo=Modulo.SCHEDULING,
                accion=ACCION_DE_BITACORA,
                entidad_afectada=f"Turno:{recordatorio.turno_id}",
                resultado=resultado,
            )
        )


def _motivo_de_descarte(
    turno: Turno | None, recordatorio: RecordatorioDeTurno, ahora: datetime
) -> str | None:
    """Por qué una fila que esperaba ya no corresponde, o `None` si sigue vigente (D-U8-4)."""
    if turno is None or not turno.esta_abierto:
        return TURNO_CERRADO
    if turno.franja.inicio != recordatorio.franja_inicio:
        return FRANJA_CAMBIADA
    if ahora >= recordatorio.franja_inicio:
        return TURNO_EMPEZADO
    return None


__all__ = ["ACCION_DE_BITACORA", "Desenlace", "EnvioDeRecordatorios"]
