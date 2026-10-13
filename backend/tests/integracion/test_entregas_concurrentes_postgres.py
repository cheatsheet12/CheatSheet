"""Dos callbacks de estado del mismo `wamid` a la vez contra el motor (U7, H2).

Un callback lee la fila, la muta en memoria y la reescribe entera. Sin un bloqueo, dos en paralelo
leen el mismo estado y el último en escribir pisa al otro: un `delivered` retrasado terminaba
borrando un `read`, y dos `failed` publicaban dos veces `recordatorio_fallido`. El arreglo es
`SELECT ... FOR UPDATE` en la búsqueda de los casos de uso de los callbacks.

El solapamiento es **determinista**, nunca con un `sleep` (mismo patrón que
`test_refresh_concurrente.py`):

* **A** es un callback abierto a mano que se queda dentro de su transacción.
* **B** es otro callback del mismo `wamid`, lanzado como tarea mientras A sigue abierto.
* El test consulta `pg_locks` como dueño hasta ver a alguien esperando un bloqueo; recién ahí A
  confirma y B termina. Antes del arreglo B no espera en la lectura sino en el `UPDATE`, y lo que
  cambia es el resultado: B sobrescribe lo que A dejó.

Sin PostgreSQL se saltean; los confirma la CI del PR.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import timedelta

import pytest
from cheatsheet.contexts.conversational.application.entregas import RegistrarEstadoDeEntrega
from cheatsheet.contexts.conversational.domain.conversacion import (
    DireccionMensaje,
    Mensaje,
    OrigenDelMensaje,
    TipoContenido,
)
from cheatsheet.contexts.conversational.domain.conversacion import (
    EstadoEntrega as EstadoDeMensaje,
)
from cheatsheet.contexts.conversational.infrastructure.repositorio_mensaje import (
    RepositorioMensajePostgres,
)
from cheatsheet.contexts.payments.application.entregas import RegistrarEntregaDeRecordatorio
from cheatsheet.contexts.payments.domain.recordatorio import (
    EstadoEntrega as EstadoDeRecordatorio,
)
from cheatsheet.contexts.payments.domain.recordatorio import Recordatorio
from cheatsheet.contexts.payments.infrastructure.repositorio_recordatorio import (
    RepositorioRecordatoriosPostgres,
)
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.auditoria import EventoAuditable
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.contexts.payments.application.test_confirmacion import PublicadorFalso
from tests.integracion.conftest import requiere_base
from tests.integracion.test_cobros_postgres import AHORA, _cliente, _cobro, _empresa, _guardar
from tests.integracion.test_conversacional_postgres import _escenario

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

_ESPERA_DE_BLOQUEO_S = 5.0
_ESPERA_DE_RESPUESTA_S = 10.0

Callback = Callable[[AsyncSession], Awaitable[None]]

# (lo que aplica A, lo que aplica B, lo que tiene que quedar): el estado más alto gana siempre.
ORDENES = [
    pytest.param("LEIDO", "ENTREGADO", "LEIDO", id="entregado-retrasado-no-pisa-a-leido"),
    pytest.param("FALLIDO", "LEIDO", "FALLIDO", id="leido-no-pisa-a-fallido"),
]


async def _hay_alguien_esperando(engine: AsyncEngine) -> bool:
    async with engine.connect() as conexion:
        cuenta = (
            await conexion.execute(text("SELECT count(*) FROM pg_locks WHERE NOT granted"))
        ).scalar_one()
    return int(cuenta) >= 1


async def _a_abierto_y_b_en_espera(
    engine: AsyncEngine,
    sesiones: async_sessionmaker[AsyncSession],
    empresa_id: EmpresaId,
    *,
    a: Callback,
    b: Callback,
) -> None:
    """A aplica y sigue abierto, B arranca y espera, A confirma, B termina."""

    async def correr_b() -> None:
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await b(sesion)

    tarea: asyncio.Task[None] | None = None
    try:
        async with sesion_de_empresa(sesiones, empresa_id) as sesion_de_a:
            await a(sesion_de_a)
            tarea = asyncio.create_task(correr_b())
            limite = asyncio.get_running_loop().time() + _ESPERA_DE_BLOQUEO_S
            while not await _hay_alguien_esperando(engine):
                assert not tarea.done(), (
                    "B terminó sin esperar ningún bloqueo: no se solapó con A "
                    "y el test no probaría nada"
                )
                assert asyncio.get_running_loop().time() < limite, "nadie esperó un bloqueo"
                await asyncio.sleep(0.02)
        await asyncio.wait_for(tarea, _ESPERA_DE_RESPUESTA_S)
    finally:
        if tarea is not None and not tarea.done():
            tarea.cancel()
            await asyncio.gather(tarea, return_exceptions=True)


# --- mensaje (agente y operador) ----------------------------------------------------------


async def _mensaje_enviado(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine, wamid: str
) -> tuple[EmpresaId, uuid.UUID]:
    escenario = await _escenario(engine_dueno, sesiones)
    mensaje = Mensaje(
        id=uuid.uuid4(),
        conversacion_id=escenario.conversacion_id,
        empresa_id=escenario.empresa_id,
        direccion=DireccionMensaje.SALIENTE,
        tipo_contenido=TipoContenido.TEXTO,
        contenido="hola",
        momento=AHORA,
        origen=OrigenDelMensaje.AGENTE,
        estado_entrega=EstadoDeMensaje.ENVIADO,
        externo_id=wamid,
    )
    async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
        await RepositorioMensajePostgres(sesion).agregar(mensaje)
    return escenario.empresa_id, mensaje.id


def _callback_de_mensaje(wamid: str, estado: str) -> Callback:
    async def aplicar(sesion: AsyncSession) -> None:
        await RegistrarEstadoDeEntrega(RepositorioMensajePostgres(sesion)).ejecutar(
            externo_id=wamid,
            estado=EstadoDeMensaje(estado),
            codigo_de_error="131047" if estado == "FALLIDO" else None,
        )

    return aplicar


@pytest.mark.parametrize(("primero", "segundo", "queda"), ORDENES)
async def test_dos_callbacks_de_un_mensaje_a_la_vez_no_se_pisan(
    sesiones: async_sessionmaker[AsyncSession],
    engine_dueno: AsyncEngine,
    primero: str,
    segundo: str,
    queda: str,
) -> None:
    wamid = f"wamid-{uuid.uuid4()}"
    empresa_id, mensaje_id = await _mensaje_enviado(sesiones, engine_dueno, wamid)

    await _a_abierto_y_b_en_espera(
        engine_dueno,
        sesiones,
        empresa_id,
        a=_callback_de_mensaje(wamid, primero),
        b=_callback_de_mensaje(wamid, segundo),
    )

    async with engine_dueno.connect() as conexion:
        fila = (
            await conexion.execute(
                text("SELECT estado_entrega, motivo_de_falla FROM mensaje WHERE id = :id"),
                {"id": mensaje_id},
            )
        ).one()
    assert fila.estado_entrega == queda
    assert fila.motivo_de_falla == ("131047" if queda == "FALLIDO" else None)


# --- recordatorio -------------------------------------------------------------------------


async def _recordatorio_enviado(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine, wamid: str
) -> tuple[EmpresaId, uuid.UUID]:
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    cobro = _cobro(empresa_id, cliente_id, vence_en_dias=0, preferencia=f"pref-{uuid.uuid4()}")
    await _guardar(sesiones, empresa_id, cobro)
    recordatorio = Recordatorio(id=uuid.uuid4(), cobro_id=cobro.id, paso=1, canal="WHATSAPP")
    recordatorio.marcar_enviado(AHORA + timedelta(days=1), externo_id=wamid)
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioRecordatoriosPostgres(sesion).agregar(recordatorio)
    return empresa_id, recordatorio.id


def _callback_de_recordatorio(
    empresa_id: EmpresaId, wamid: str, estado: str, publicador: PublicadorFalso
) -> Callback:
    async def aplicar(sesion: AsyncSession) -> None:
        await RegistrarEntregaDeRecordatorio(
            recordatorios=RepositorioRecordatoriosPostgres(sesion), publicador=publicador
        ).ejecutar(
            empresa_id=empresa_id,
            externo_id=wamid,
            estado=EstadoDeRecordatorio(estado),
            codigo_de_error="131047" if estado == "FALLIDO" else None,
            ahora=AHORA,
        )

    return aplicar


async def _estado_del_recordatorio(
    engine: AsyncEngine, recordatorio_id: uuid.UUID
) -> tuple[str, str | None]:
    async with engine.connect() as conexion:
        fila = (
            await conexion.execute(
                text("SELECT estado_entrega, ultimo_error FROM recordatorio WHERE id = :id"),
                {"id": recordatorio_id},
            )
        ).one()
    return fila.estado_entrega, fila.ultimo_error


@pytest.mark.parametrize(("primero", "segundo", "queda"), ORDENES)
async def test_dos_callbacks_de_un_recordatorio_a_la_vez_no_se_pisan(
    sesiones: async_sessionmaker[AsyncSession],
    engine_dueno: AsyncEngine,
    primero: str,
    segundo: str,
    queda: str,
) -> None:
    wamid = f"wamid-{uuid.uuid4()}"
    empresa_id, recordatorio_id = await _recordatorio_enviado(sesiones, engine_dueno, wamid)

    await _a_abierto_y_b_en_espera(
        engine_dueno,
        sesiones,
        empresa_id,
        a=_callback_de_recordatorio(empresa_id, wamid, primero, PublicadorFalso()),
        b=_callback_de_recordatorio(empresa_id, wamid, segundo, PublicadorFalso()),
    )

    estado, error = await _estado_del_recordatorio(engine_dueno, recordatorio_id)
    assert estado == queda
    assert error == ("131047" if queda == "FALLIDO" else None)


async def test_dos_failed_a_la_vez_publican_recordatorio_fallido_una_sola_vez(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    wamid = f"wamid-{uuid.uuid4()}"
    empresa_id, recordatorio_id = await _recordatorio_enviado(sesiones, engine_dueno, wamid)
    publicador_de_a, publicador_de_b = PublicadorFalso(), PublicadorFalso()

    await _a_abierto_y_b_en_espera(
        engine_dueno,
        sesiones,
        empresa_id,
        a=_callback_de_recordatorio(empresa_id, wamid, "FALLIDO", publicador_de_a),
        b=_callback_de_recordatorio(empresa_id, wamid, "FALLIDO", publicador_de_b),
    )

    publicados = [*publicador_de_a.eventos, *publicador_de_b.eventos]
    assert [evento.accion for evento in publicados if isinstance(evento, EventoAuditable)] == [
        "recordatorio_fallido"
    ]
    assert len(publicados) == 1
    assert (await _estado_del_recordatorio(engine_dueno, recordatorio_id))[0] == "FALLIDO"
