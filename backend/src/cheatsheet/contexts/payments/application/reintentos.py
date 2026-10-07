"""El envío de un recordatorio, en tres tiempos, y su reintento acotado (U7, tramo ii, D-U7-3).

**Por qué tres tiempos.** El barrido corre en la unidad de trabajo de la empresa, que confirma recién
al final. Si insertaba la fila, llamaba a Meta y guardaba el resultado todo ahí adentro, un callback
`failed` o `delivered` que llegara antes del commit no encontraba la fila y se perdía (H1,
`TODO.md` §22.57), y la llamada a Meta corría con escrituras sin confirmar (G5, ADR-0014). Ahora:

1. **Reservar** (transacción corta): se **prepara** el mensaje (lee el contacto y la plantilla) y se
   escribe la fila con el intento ya contado (`intentos = n`, `proximo_intento_en = reloj.ahora() +
   VENTANA_DE_ENVIO`), todo en un savepoint, y se **confirma**. Si preparar falla en la base, no
   queda fila y el barrido siguiente lo evalúa de nuevo (nunca queda `INCIERTO` sin haber salido).
2. **Mandar**: se relee el cobro (si se pagó o cerró mientras tanto se descarta) y se llama a Meta.
   **Sin escrituras sin confirmar, sin locks y sin ninguna otra lectura de base**: `PortTransaccion`
   vuelve a declarar la empresa, lo que abre una transacción nueva y vacía, así que la afirmación
   exacta no es «sin transacción abierta» sino esa (N1).
3. **Registrar** (otra transacción corta): el resultado —`wamid`, estado, error— y se confirma.

**El reloj.** El `ahora` del barrido solo decide *qué* le toca a esta corrida. Toda fecha que se
**escribe** (la ventana de la reserva, `enviado_en`, la espera del reintento, el evento) sale del
reloj real en ese momento: un barrido largo no reserva con una hora vieja, y un barrido solapado no
da por perdida una reserva cuya ventana todavía corre (S2).

**Ventanas de caída y cómo se resuelve cada una.** La fila nunca se vuelve a mandar si un envío pudo
haber salido: un duplicado de un recordatorio es peor que uno que falta (ADR-0011 punto 6).

- Cae **antes** de reservar o falla el commit de la reserva: no hay fila y **nada pudo salir**, salvo
  que la base haya confirmado y no lo haya dicho (commit ambiguo): entonces la fila queda en curso y
  se resuelve `INCIERTO` al vencer su ventana **sin haber mandado nada** (N4: seguro, un falso
  `FALLIDO`, nunca un duplicado). Si no hay fila, la hora siguiente lo evalúa como un paso nuevo.
- Cae **después de reservar y antes de llamar a Meta**: la fila queda «en curso» con su ventana. No se
  puede distinguir de la siguiente, así que se trata igual.
- Cae **después de que Meta aceptó y antes de registrar** (o falla el commit del resultado): ídem.
  Vencida la ventana, el siguiente barrido la resuelve `FALLIDO` con motivo `INCIERTO` y **no la
  reenvía**, que es lo mismo que el canal hace con un timeout de lectura (`EnvioIncierto`).
- Una fila **sin intentar** (`intentos = 0`: ningún envío empezó, nada pudo salir) sí se manda; es lo
  que desata una cadena trabada por una fila sin `enviado_en` (caso 4).

**Si la primera confirmación falla** (N5), lo no confirmado hasta ahí —por ejemplo los cobros que
`VencerCobros` movió a `VENCIDO` en el mismo barrido— se deshace y se rehace en el barrido siguiente.
**Si `confirmar()` no puede volver a declarar la empresa** (N6), puede escapar un `SQLAlchemyError`
crudo; con la empresa sin declarar RLS no deja ver ni escribir nada, así que es seguro y la tarea de
esa empresa falla sola.

**Reintento.** Solo una falla marcada **transitoria** (`ResultadoDeEnvio.transitoria`) vuelve a
intentarse, sobre la **misma fila** (un `UPDATE`, nunca un `INSERT`: la idempotencia de RN-05 es el
índice `(cobro_id, paso)`), hasta `REINTENTOS_MAXIMOS` intentos con espera de 1 h, 2 h. Un rechazo
permanente, un resultado incierto o un `failed` por callback no se reintentan.

**Un recordatorio por cobro por barrido.** `reintentar_pendientes` informa de qué cobros tocó, y el
despacho de pasos nuevos se salta los que ya tuvieron un desenlace en la pasada 1.

**Atomicidad por ítem.** Cada reserva y cada registro corren en su propio savepoint
(`PortAislamiento`) y se confirman con `PortTransaccion`: lo que la base rechaza deshace solo ese
ítem.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from enum import StrEnum
from typing import TypeVar
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
    MensajeListo,
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
from cheatsheet.shared.clock import Reloj
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.events import PublicadorDeEventos

logger = obtener_logger(__name__)

_T = TypeVar("_T")


class Desenlace(StrEnum):
    """Cómo terminó el trato con una fila, para los contadores del barrido."""

    SALIO = "SALIO"
    FALLO = "FALLO"
    EN_REINTENTO = "EN_REINTENTO"
    #: No se mandó nada ni se cambió el resultado (otro barrido la tenía, o se descartó).
    NADA = "NADA"
    #: No se pudo registrar lo que pasó (o revisar el cobro): la fila queda «en curso». Si Meta
    #: pudo haberlo recibido se resolverá `INCIERTO` y no se reenvía; si no se llamó, es seguro.
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
        reloj: Reloj,
    ) -> None:
        self._cobros = cobros
        self._recordatorios = recordatorios
        self._envio = envio
        self._publicador = publicador
        self._aislamiento = aislamiento
        self._transaccion = transaccion
        self._reloj = reloj

    # ------------------------------------------------------------------ paso nuevo

    async def enviar_nuevo(
        self, *, empresa_id: EmpresaId, cobro: Cobro, canal: str, numero: int
    ) -> Desenlace:
        """El primer intento de un paso que todavía no tiene fila."""
        recordatorio = Recordatorio(id=uuid4(), cobro_id=cobro.id, paso=numero, canal=canal)

        async def reservar() -> MensajeListo | ResultadoDeEnvio:
            # Primero se lee (preparar), después se escribe: si la lectura falla, no hay fila.
            preparado = await self._envio.preparar(
                empresa_id=empresa_id, cobro=cobro, canal=canal, paso=numero
            )
            recordatorio.iniciar_intento(self._reloj.ahora())
            await self._recordatorios.agregar(recordatorio)
            return preparado

        reservado = await self._reservado(reservar, cobro_id=str(cobro.id), paso=numero)
        if isinstance(reservado, Desenlace):
            return reservado
        return await self._mandar_y_registrar(empresa_id, recordatorio, reservado)

    # ------------------------------------------------------------------ fila existente

    async def retomar(
        self, *, empresa_id: EmpresaId, recordatorio_id: UUID, ahora: datetime
    ) -> Desenlace:
        """Toma una fila ya existente que le toca a este barrido: sin intentar o con su fecha.

        La relee **bloqueada**: si otro barrido la tomó mientras tanto, ya no le toca y se deja.
        `ahora` solo decide si le toca; lo que se escribe sale del reloj real.
        """
        tomada = await self._reservado(
            lambda: self._tomar(empresa_id, recordatorio_id, ahora),
            recordatorio_id=str(recordatorio_id),
        )
        if isinstance(tomada, Desenlace):
            return tomada
        recordatorio, preparado = tomada
        return await self._mandar_y_registrar(empresa_id, recordatorio, preparado)

    async def reintentar_pendientes(
        self, *, empresa_id: EmpresaId, ahora: datetime
    ) -> list[tuple[UUID, Desenlace]]:
        """Las filas que esperan un reintento o cuyo envío en curso venció, con su fecha cumplida.

        Devuelve `(cobro_id, desenlace)` de cada una: el despacho de pasos nuevos no vuelve a tocar
        un cobro que ya tuvo su recordatorio en esta corrida (N7).
        """
        desenlaces: list[tuple[UUID, Desenlace]] = []
        for pendiente in await self._recordatorios.pendientes_de_reintento(ahora):
            desenlace = await self.retomar(
                empresa_id=empresa_id, recordatorio_id=pendiente.id, ahora=ahora
            )
            desenlaces.append((pendiente.cobro_id, desenlace))
        return desenlaces

    async def _reservado(
        self, bloque: Callable[[], Awaitable[_T]], **datos: str | int
    ) -> _T | Desenlace:
        """Corre `bloque` en un savepoint y lo confirma. Si no se pudo, `Desenlace.NADA`.

        Nada de lo que falle acá deja una fila a medias: el savepoint se deshace entero.
        """
        try:
            async with self._aislamiento.aislar():
                resultado = await bloque()
        except RecordatorioDuplicado:
            # Otro barrido llegó primero. **No es un error**: significa «esto ya salió», que es
            # exactamente lo que RN-05 pide garantizar.
            logger.info("recordatorio_ya_despachado", **datos)
            return Desenlace.NADA
        except DespachoNoPersistido:
            # Sin la fila confirmada no hay E/S: nada pudo salir. Sin datos del cliente ni del error.
            logger.warning("recordatorio_no_persistido", **datos)
            return Desenlace.NADA
        except Exception as exc:  # noqa: BLE001 — ver abajo
            # Un adaptador que rompe el contrato de `preparar` (solo puede levantar lo que la base
            # rechaza). El savepoint ya se deshizo: no hay fila y el resto del barrido sigue.
            logger.warning("recordatorio_no_preparado", **datos, causa=type(exc).__name__)
            return Desenlace.NADA
        try:
            await self._transaccion.confirmar()
        except DespachoNoPersistido:
            logger.warning("recordatorio_no_persistido", **datos)
            return Desenlace.NADA
        return resultado

    async def _tomar(
        self, empresa_id: EmpresaId, recordatorio_id: UUID, ahora: datetime
    ) -> tuple[Recordatorio, MensajeListo | ResultadoDeEnvio] | Desenlace:
        """Decide qué hacer con la fila bloqueada. Devuelve el intento a mandar, o cómo terminó."""
        recordatorio = await self._recordatorios.buscar_para_actualizar(recordatorio_id)
        if recordatorio is None or not recordatorio.corresponde_intentar(ahora):
            return Desenlace.NADA
        if recordatorio.envio_perdido(ahora):
            # Un envío empezó y nunca registró su resultado: Meta pudo haberlo aceptado.
            ahora_real = self._reloj.ahora()
            recordatorio.fallar(ahora_real, INCIERTO)
            await self._recordatorios.guardar(recordatorio)
            await self._publicar(empresa_id, recordatorio.cobro_id, ahora_real, Resultado.ERROR)
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
        # Se prepara **antes** de escribir: si la lectura falla, la fila queda como estaba y el
        # barrido siguiente la retoma (S1).
        preparado = await self._envio.preparar(
            empresa_id=empresa_id, cobro=cobro, canal=recordatorio.canal, paso=recordatorio.paso
        )
        recordatorio.iniciar_intento(self._reloj.ahora())
        await self._recordatorios.guardar(recordatorio)
        return recordatorio, preparado

    # ------------------------------------------------------------------ mandar y registrar

    async def _mandar_y_registrar(
        self,
        empresa_id: EmpresaId,
        recordatorio: Recordatorio,
        preparado: MensajeListo | ResultadoDeEnvio,
    ) -> Desenlace:
        if isinstance(preparado, ResultadoDeEnvio):
            resultado = (
                preparado  # ya se sabe que no puede salir (sin teléfono, canal sin adaptador)
            )
        else:
            cerrado = await self._cobro_cerrado_entretanto(recordatorio)
            if cerrado is not None:
                return cerrado
            # **Sin escrituras sin confirmar ni locks, y sin leer la base**: la reserva ya se
            # confirmó (`PortTransaccion`) y el mensaje ya está armado.
            resultado = await self._mandar(preparado)
        try:
            async with self._aislamiento.aislar():
                desenlace = await self._registrar(empresa_id, recordatorio, resultado)
            await self._transaccion.confirmar()
        except DespachoNoPersistido:
            # La fila sigue «en curso» y se resolverá `INCIERTO` al vencer su ventana: no se manda
            # otra vez lo que pudo haber salido. Sin datos del cliente ni del error.
            logger.warning(
                "recordatorio_resultado_no_persistido",
                cobro_id=str(recordatorio.cobro_id),
                paso=recordatorio.paso,
            )
            return Desenlace.SIN_REGISTRAR
        return desenlace

    async def _cobro_cerrado_entretanto(self, recordatorio: Recordatorio) -> Desenlace | None:
        """N2: después de reservar, vuelve a leer el cobro; si se pagó o cerró, no se manda.

        Devuelve `None` si el cobro sigue abierto. Si no, la fila se descarta (la misma regla de
        `_tomar`) y devuelve cómo terminó. Si la lectura falla en la base, **no se manda** y la fila
        queda «en curso» (se resolverá `INCIERTO` sin haber salido nada, como en N4).
        """
        try:
            async with self._aislamiento.aislar():
                cobro = await self._cobros.buscar_por_id(recordatorio.cobro_id)
                if cobro is not None and cobro.recibe_recordatorios:
                    return None
                recordatorio.descartar()
                await self._recordatorios.guardar(recordatorio)
            await self._transaccion.confirmar()
        except DespachoNoPersistido:
            logger.warning(
                "recordatorio_no_revisado",
                cobro_id=str(recordatorio.cobro_id),
                paso=recordatorio.paso,
            )
            return Desenlace.SIN_REGISTRAR
        return Desenlace.NADA

    async def _mandar(self, mensaje: MensajeListo) -> ResultadoDeEnvio:
        try:
            return await self._envio.mandar(mensaje)
        except Exception as exc:  # noqa: BLE001 — ver abajo
            # `Exception` es lo que `CLAUDE.md` §5 prohíbe en general, y acá está acotado por el
            # motivo: el puerto lo implementan adaptadores que podrían levantar cualquier cosa, y
            # su contrato dice que no deben. Es defensa en profundidad: el paso queda `FALLIDO` y,
            # al no ser transitorio, no se reintenta. Sólo la clase de la excepción, nunca su texto.
            logger.warning(
                "recordatorio_envio_fallido",
                cobro_id=str(mensaje.cobro_id),
                paso=mensaje.paso,
                causa=type(exc).__name__,
            )
            return ResultadoDeEnvio(estado=EstadoEntrega.FALLIDO, codigo="ERROR")

    async def _registrar(
        self,
        empresa_id: EmpresaId,
        recordatorio: Recordatorio,
        resultado: ResultadoDeEnvio,
    ) -> Desenlace:
        ahora = self._reloj.ahora()  # el de ahora, no el del inicio del barrido (S2)
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
