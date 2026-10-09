"""El barrido de recordatorios de turno contra el motor (U8, casos 25, 29 y 30).

Tres cosas que solo existen con transacciones reales:

- **Caso 25 (G5/H1).** Cuando el barrido llama al canal, la fila del recordatorio **ya está confirmada**:
  otra transacción (la de un callback) la ve, y no queda ninguna escritura sin confirmar.
- **Caso 29.** El recordatorio queda como mensaje `SISTEMA` en el hilo del cliente, y otra transacción
  (un callback posterior al commit) lo encuentra por `wamid`.
- **Caso 30.** Dos barridos solapados de la misma empresa mandan **un** solo mensaje: los nuevos se
  frenan en el índice único y los reintentos en la fila releída bloqueada (`FOR UPDATE`).

Sin PostgreSQL se saltean; los confirma la CI del PR.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta

import pytest
from cheatsheet.api.avisos_de_turno import CanalDeAvisosViaConversacion
from cheatsheet.contexts.conversational.application.notificaciones import NotificarAlCliente
from cheatsheet.contexts.conversational.infrastructure.repositories import (
    RepositorioConversacionPostgres,
)
from cheatsheet.contexts.conversational.infrastructure.repositorio_mensaje import (
    RepositorioMensajePostgres,
)
from cheatsheet.contexts.scheduling.application.envio_de_recordatorios import EnvioDeRecordatorios
from cheatsheet.contexts.scheduling.application.ports import ServicioAgendable
from cheatsheet.contexts.scheduling.application.ports_de_recordatorios import (
    RecordatorioListo,
    ResultadoDelEnvio,
    SinTelefono,
)
from cheatsheet.contexts.scheduling.application.recordatorios import EnviarRecordatoriosDeTurno
from cheatsheet.contexts.scheduling.domain.recordatorio_de_turno import (
    VENTANA_DE_ENVIO,
    RecordatorioDeTurno,
)
from cheatsheet.contexts.scheduling.domain.turno import Turno
from cheatsheet.contexts.scheduling.infrastructure.recordatorio_por_whatsapp import (
    RecordatorioPorWhatsApp,
)
from cheatsheet.contexts.scheduling.infrastructure.repositories import RepositorioTurnoPostgres
from cheatsheet.contexts.scheduling.infrastructure.repositorio_de_recordatorios import (
    RepositorioRecordatoriosDeTurnoPostgres,
)
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.platform.transaccion import AislamientoConSavepoint, ConfirmacionDeLaUnidad
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.contexts.scheduling.application.dobles_de_recordatorios import (
    AgendaFalsa,
    EnvioGuionado,
    PublicadorFalso,
    TransaccionFalsa,
    enviado,
    transitoria,
)
from tests.integracion.conftest import requiere_base
from tests.integracion.test_recordatorios_de_turno_postgres import (
    INICIO,
    Escenario,
    _escenario,
    _guardar_turno,
)

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

#: Un instante dentro de la ventana de 24 h del turno de `INICIO`.
BARRIDO = INICIO - timedelta(hours=23)

FILAS = text(
    "SELECT id, intentos, resultado, ultimo_error, proximo_intento_en "
    "FROM recordatorio_de_turno ORDER BY created_at, id"
)
MENSAJES = text("SELECT externo_id, origen, direccion FROM mensaje WHERE externo_id = :wamid")


class _Compuerta:
    """Un punto de encuentro: retiene a quien llega hasta que llegan `cuantos`, o vence el tiempo.

    Es lo que fuerza la carrera: sin él, `gather` puede correr un barrido entero antes de que el otro
    arranque y el candado nunca se ejercita. El tiempo de espera evita que un test colgado cuelgue la CI.
    """

    def __init__(self, cuantos: int = 2) -> None:
        self._cuantos = cuantos
        self.llegaron = 0
        self._lista = asyncio.Event()

    def llegar(self) -> None:
        if self.llegaron >= self._cuantos:
            return  # solo cuentan las primeras llegadas: las relecturas posteriores no son la carrera
        self.llegaron += 1
        if self.llegaron >= self._cuantos:
            self._lista.set()

    async def esperar(self) -> None:
        await asyncio.wait_for(self._lista.wait(), timeout=15)


class _RecordatoriosVigilados(RepositorioRecordatoriosDeTurnoPostgres):
    """Avisa cada vez que un barrido pide la fila **bloqueada**, antes de que la base lo haga esperar."""

    def __init__(self, sesion: AsyncSession, al_pedir_el_bloqueo: Callable[[], None]) -> None:
        super().__init__(sesion)
        self._al_pedir_el_bloqueo = al_pedir_el_bloqueo

    async def buscar_para_actualizar(
        self, recordatorio_id: uuid.UUID
    ) -> RecordatorioDeTurno | None:
        self._al_pedir_el_bloqueo()
        return await super().buscar_para_actualizar(recordatorio_id)


def _barrido(
    sesion: AsyncSession,
    empresa_id: EmpresaId,
    envio: EnvioGuionado | RecordatorioPorWhatsApp,
    ahora: datetime,
    al_pedir_el_bloqueo: Callable[[], None] | None = None,
) -> EnviarRecordatoriosDeTurno:
    turnos = RepositorioTurnoPostgres(sesion)
    recordatorios = (
        RepositorioRecordatoriosDeTurnoPostgres(sesion)
        if al_pedir_el_bloqueo is None
        else _RecordatoriosVigilados(sesion, al_pedir_el_bloqueo)
    )
    return EnviarRecordatoriosDeTurno(
        turnos=turnos,
        recordatorios=recordatorios,
        agenda=AgendaFalsa(),
        envio=EnvioDeRecordatorios(
            turnos=turnos,
            recordatorios=recordatorios,
            envio=envio,
            publicador=PublicadorFalso(),
            aislamiento=AislamientoConSavepoint(sesion),
            transaccion=ConfirmacionDeLaUnidad(sesion, empresa_id),
            reloj=RelojFijo(ahora),
        ),
    )


async def _barrer(
    sesiones: async_sessionmaker[AsyncSession],
    empresa_id: EmpresaId,
    envio: EnvioGuionado,
    ahora: datetime,
    al_pedir_el_bloqueo: Callable[[], None] | None = None,
) -> None:
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await _barrido(sesion, empresa_id, envio, ahora, al_pedir_el_bloqueo).ejecutar(
            empresa_id=empresa_id, ahora=ahora
        )


async def _filas(
    sesiones: async_sessionmaker[AsyncSession], empresa_id: EmpresaId
) -> list[tuple[object, ...]]:
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        return [tuple(fila) for fila in await sesion.execute(FILAS)]


async def _con_un_turno(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> Escenario:
    escenario = await _escenario(engine_dueno, sesiones)
    await _guardar_turno(sesiones, escenario, escenario.turno())
    return escenario


async def test_cuando_el_barrido_llama_al_canal_la_fila_ya_esta_confirmada_para_otra_transaccion(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """**Caso 25.** Lo que ve un callback `failed` o `delivered` que llegue durante el barrido."""
    escenario = await _con_un_turno(sesiones, engine_dueno)
    vistas: list[list[tuple[object, ...]]] = []
    envio = EnvioGuionado(TransaccionFalsa(), enviado())
    original = envio.mandar

    async def mandar_mirando(listo: RecordatorioListo) -> ResultadoDelEnvio:
        # Otra transacción, otra conexión: solo ve lo que el barrido ya confirmó.
        vistas.append(await _filas(sesiones, escenario.empresa_id))
        return await original(listo)

    envio.mandar = mandar_mirando  # type: ignore[method-assign]  # el doble sustituye el método para mirar/forzar la carrera
    await _barrer(sesiones, escenario.empresa_id, envio, BARRIDO)

    (visto,) = vistas
    assert len(visto) == 1
    _, intentos, resultado, error, proximo = visto[0]
    assert (intentos, resultado, error) == (1, None, None)
    assert proximo == BARRIDO + VENTANA_DE_ENVIO
    (final,) = await _filas(sesiones, escenario.empresa_id)
    assert final[2] == "ENVIADO"


async def test_el_reintento_actualiza_la_misma_fila(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """**Caso 22** contra el motor: el reintento es un `UPDATE`, nunca un `INSERT`."""
    escenario = await _con_un_turno(sesiones, engine_dueno)
    envio = EnvioGuionado(TransaccionFalsa(), transitoria(), enviado())

    await _barrer(sesiones, escenario.empresa_id, envio, BARRIDO)
    (espera,) = await _filas(sesiones, escenario.empresa_id)
    assert (espera[1], espera[2], espera[3]) == (1, None, "SATURADA")
    assert espera[4] == BARRIDO + timedelta(minutes=15)

    await _barrer(sesiones, escenario.empresa_id, envio, BARRIDO + timedelta(minutes=15))

    (final,) = await _filas(sesiones, escenario.empresa_id)
    assert final[0] == espera[0]
    assert (final[1], final[2], final[4]) == (2, "ENVIADO", None)
    assert len(envio.enviados) == 2


async def test_dos_barridos_solapados_de_la_misma_empresa_mandan_una_sola_vez(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """**Caso 30.** Los dos workers encuentran el mismo turno a la vez: gana el índice único.

    El primero que llega a `preparar` espera al segundo: así **los dos** leyeron «no hay fila» antes de
    que alguno inserte, y la clave única es lo único que decide quién manda.
    """
    escenario = await _con_un_turno(sesiones, engine_dueno)
    envio = EnvioGuionado(TransaccionFalsa(), enviado(), enviado())
    compuerta = _Compuerta()
    preparar = envio.preparar

    async def preparar_en_la_compuerta(
        turno: Turno, anticipacion_min: int
    ) -> RecordatorioListo | SinTelefono:
        compuerta.llegar()
        await compuerta.esperar()
        return await preparar(turno, anticipacion_min)

    envio.preparar = preparar_en_la_compuerta  # type: ignore[method-assign]  # el doble sustituye el método para mirar/forzar la carrera
    await asyncio.gather(
        _barrer(sesiones, escenario.empresa_id, envio, BARRIDO),
        _barrer(sesiones, escenario.empresa_id, envio, BARRIDO),
    )

    assert compuerta.llegaron == 2  # los dos llegaron: la carrera existió
    assert len(envio.enviados) == 1
    (fila,) = await _filas(sesiones, escenario.empresa_id)
    assert fila[2] == "ENVIADO"


async def test_dos_barridos_solapados_sobre_un_reintento_pendiente_mandan_una_sola_vez(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """**Caso 30**, la otra mitad: la fila espera su reintento y la relee bloqueada el que llega.

    El que tiene el candado espera, **dentro de él**, a que el otro lo pida: el otro queda bloqueado en
    la base, y al soltarse relee una fila que ya no le toca. Sin `FOR UPDATE` los dos la verían vencida.
    """
    escenario = await _con_un_turno(sesiones, engine_dueno)
    await _barrer(
        sesiones, escenario.empresa_id, EnvioGuionado(TransaccionFalsa(), transitoria()), BARRIDO
    )
    envio = EnvioGuionado(TransaccionFalsa(), enviado(), enviado())
    cuando = BARRIDO + timedelta(minutes=15)
    compuerta = _Compuerta()
    preparar = envio.preparar

    async def preparar_con_el_otro_esperando(
        turno: Turno, anticipacion_min: int
    ) -> RecordatorioListo | SinTelefono:
        await compuerta.esperar()  # sigue con el candado tomado hasta que el otro lo pida
        return await preparar(turno, anticipacion_min)

    envio.preparar = preparar_con_el_otro_esperando  # type: ignore[method-assign]  # el doble sustituye el método para mirar/forzar la carrera
    await asyncio.gather(
        _barrer(sesiones, escenario.empresa_id, envio, cuando, compuerta.llegar),
        _barrer(sesiones, escenario.empresa_id, envio, cuando, compuerta.llegar),
    )

    assert compuerta.llegaron == 2  # los dos pidieron el candado
    assert len(envio.enviados) == 1
    (fila,) = await _filas(sesiones, escenario.empresa_id)
    assert (fila[1], fila[2]) == (2, "ENVIADO")


class _Clientes:
    def __init__(self, nombre: str, telefono: str) -> None:
        self._contacto = (nombre, telefono)

    async def contacto_de(self, cliente_id: uuid.UUID) -> tuple[str, str] | None:
        del cliente_id
        return self._contacto


class _Servicios:
    async def buscar_agendable(self, servicio_id: uuid.UUID) -> ServicioAgendable | None:
        return ServicioAgendable(id=servicio_id, nombre="Corte", duracion_estandar_min=30)

    async def listar_agendables(self) -> list[ServicioAgendable]:
        return []


class _SinPlantillas:
    async def para(self, codigo: str, variables: Mapping[str, str]) -> None:
        del codigo, variables
        return


class _Mensajeria:
    async def enviar(self, *, telefono: str, texto: str) -> str:
        del telefono, texto
        return "wamid.RECORDATORIO"

    async def enviar_plantilla(
        self, *, telefono: str, nombre: str, idioma: str, parametros: Mapping[str, str]
    ) -> str:
        del telefono, nombre, idioma, parametros
        return "wamid.RECORDATORIO"


async def test_el_recordatorio_queda_como_mensaje_del_sistema_y_un_callback_lo_encuentra_por_wamid(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """**Caso 29.** Camino real: adaptador de WhatsApp → `NotificarAlCliente` → hilo del cliente."""
    escenario = await _con_un_turno(sesiones, engine_dueno)
    reloj = RelojFijo(BARRIDO)

    async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
        canal = CanalDeAvisosViaConversacion(
            NotificarAlCliente(
                conversaciones=RepositorioConversacionPostgres(sesion),
                mensajes=RepositorioMensajePostgres(sesion),
                mensajeria=_Mensajeria(),
                aislar=sesion.begin_nested,
            ),
            empresa_id=escenario.empresa_id,
            reloj=reloj,
        )
        envio = RecordatorioPorWhatsApp(
            clientes=_Clientes("Ana Diaz", "5491112345678"),
            servicios=_Servicios(),
            canal=canal,
            plantillas=_SinPlantillas(),
        )
        await _barrido(sesion, escenario.empresa_id, envio, BARRIDO).ejecutar(
            empresa_id=escenario.empresa_id, ahora=BARRIDO
        )

    # Otra transacción, después del commit: lo que haría el callback de estado de Meta.
    async with sesion_de_empresa(sesiones, escenario.empresa_id) as otra:
        filas = (await otra.execute(MENSAJES, {"wamid": "wamid.RECORDATORIO"})).all()
    assert [tuple(fila) for fila in filas] == [("wamid.RECORDATORIO", "SISTEMA", "SALIENTE")]
    (fila,) = await _filas(sesiones, escenario.empresa_id)
    assert fila[2] == "ENVIADO"
