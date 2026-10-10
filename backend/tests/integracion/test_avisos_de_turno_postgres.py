"""Los avisos de turno guardados como mensaje del sistema, contra el motor (U7, casos 3, 24, 25 y 27).

Lo que un doble no demuestra: que la escritura corre en un **savepoint real** (un rechazo de la
base no aborta la transacción de la operación del panel), que el hilo del aviso es el mismo que
retoma el agente y que RLS acota todo a la empresa. Se usan los repositorios reales de
`conversational` y un canal de mentira (sin red).

Sin PostgreSQL se saltean; los confirma la CI del PR.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

import pytest
from cheatsheet.contexts.conversational.application.errors import MensajeRechazado
from cheatsheet.contexts.conversational.application.notificaciones import (
    EnvioDeAviso,
    NotificarAlCliente,
    ResultadoDeNotificacion,
)
from cheatsheet.contexts.conversational.domain.conversacion import (
    EstadoConversacion,
    EstadoEntrega,
    OrigenDelMensaje,
)
from cheatsheet.contexts.conversational.infrastructure.repositories import (
    RepositorioConversacionPostgres,
)
from cheatsheet.contexts.conversational.infrastructure.repositorio_mensaje import (
    RepositorioMensajePostgres,
)
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

AHORA = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)
TEXTO = "Hola Ana Diaz, tu turno fue cancelado."
CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")
CREAR_CLIENTE = text(
    "INSERT INTO cliente (id, empresa_id, nombre, origen, activo, created_at, updated_at) "
    "VALUES (:id, :empresa_id, 'Ana Diaz', 'AGENTE', true, :ahora, :ahora)"
)


class Canal:
    def __init__(self, *wamids: str, falla: Exception | None = None) -> None:
        self._wamids = list(wamids)
        self._falla = falla

    async def enviar(self, *, telefono: str, texto: str) -> str:
        del telefono, texto
        if self._falla is not None:
            raise self._falla
        return self._wamids.pop(0)

    async def enviar_plantilla(
        self, *, telefono: str, nombre: str, idioma: str, parametros: Mapping[str, str]
    ) -> str:
        del telefono, nombre, idioma, parametros
        raise AssertionError("estos avisos salen como texto")


async def _empresa_con_cliente(engine_dueno: AsyncEngine) -> tuple[EmpresaId, uuid.UUID]:
    empresa_id = EmpresaId(uuid.uuid4())
    cliente_id = uuid.uuid4()
    async with engine_dueno.begin() as conexion:
        await conexion.execute(CREAR_EMPRESA, {"id": empresa_id})
        await conexion.execute(
            CREAR_CLIENTE, {"id": cliente_id, "empresa_id": empresa_id, "ahora": AHORA}
        )
    return empresa_id, cliente_id


def _caso(sesion: AsyncSession, canal: Canal) -> NotificarAlCliente:
    return NotificarAlCliente(
        conversaciones=RepositorioConversacionPostgres(sesion),
        mensajes=RepositorioMensajePostgres(sesion),
        mensajeria=canal,
        aislar=sesion.begin_nested,
    )


async def _avisar(
    caso: NotificarAlCliente, empresa_id: EmpresaId, cliente_id: uuid.UUID
) -> ResultadoDeNotificacion:
    return await caso.ejecutar(
        empresa_id=empresa_id,
        cliente_id=cliente_id,
        telefono="5491112345678",
        envio=EnvioDeAviso(texto=TEXTO),
        ahora=AHORA,
    )


async def test_el_aviso_queda_en_una_conversacion_activa_del_cliente(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """**Caso 3.** Sin hilo previo se crea uno `ACTIVA`; un segundo aviso se agrega al mismo."""
    empresa_id, cliente_id = await _empresa_con_cliente(engine_dueno)
    wamid = f"wamid-{uuid.uuid4()}"
    otro = f"wamid-{uuid.uuid4()}"

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        caso = _caso(sesion, Canal(wamid, otro))
        await _avisar(caso, empresa_id, cliente_id)
        await _avisar(caso, empresa_id, cliente_id)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        hilo = await RepositorioConversacionPostgres(sesion).abierta_de(cliente_id)
        assert hilo is not None
        mensajes = await RepositorioMensajePostgres(sesion).del_hilo(hilo.id)
    assert hilo.estado is EstadoConversacion.ACTIVA
    assert [(m.origen, m.externo_id) for m in mensajes] == [
        (OrigenDelMensaje.SISTEMA, wamid),
        (OrigenDelMensaje.SISTEMA, otro),
    ]
    assert {m.estado_entrega for m in mensajes} == {EstadoEntrega.ENVIADO}


async def test_un_rechazo_de_meta_deja_el_aviso_fallido_con_su_motivo(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """**Caso 24.**"""
    empresa_id, cliente_id = await _empresa_con_cliente(engine_dueno)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        resultado = await _avisar(
            _caso(sesion, Canal(falla=MensajeRechazado("no", codigo=131047))),
            empresa_id,
            cliente_id,
        )

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        hilo = await RepositorioConversacionPostgres(sesion).abierta_de(cliente_id)
        assert hilo is not None
        (aviso,) = await RepositorioMensajePostgres(sesion).del_hilo(hilo.id)
    assert resultado.falla == "131047"
    assert (aviso.estado_entrega, aviso.motivo_de_falla) == (EstadoEntrega.FALLIDO, "131047")


async def test_un_rechazo_de_la_base_no_aborta_la_transaccion_de_la_operacion(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """**Caso 25 (savepoint real).** Un `wamid` repetido viola `uq_mensaje_externo_id`.

    El segundo aviso no se guarda, pero lo hecho antes en la misma transacción (el primer aviso) y
    lo que se haga después (una consulta) siguen valiendo: el turno queda cancelado igual.
    """
    empresa_id, cliente_id = await _empresa_con_cliente(engine_dueno)
    repetido = f"wamid-{uuid.uuid4()}"

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        caso = _caso(sesion, Canal(repetido, repetido))
        primero = await _avisar(caso, empresa_id, cliente_id)
        segundo = await _avisar(caso, empresa_id, cliente_id)
        # La transacción sigue usable después del rechazo.
        hilo = await RepositorioConversacionPostgres(sesion).abierta_de(cliente_id)

    assert primero.sin_registrar is False
    assert segundo.enviado is True
    assert segundo.sin_registrar is True
    assert hilo is not None
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        mensajes = await RepositorioMensajePostgres(sesion).del_hilo(hilo.id)
    assert [m.externo_id for m in mensajes] == [repetido]


async def test_el_aviso_de_una_empresa_no_aparece_en_otra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """RLS: el hilo y el aviso de A no existen para B."""
    empresa_a, cliente_a = await _empresa_con_cliente(engine_dueno)
    empresa_b, _ = await _empresa_con_cliente(engine_dueno)
    wamid = f"wamid-{uuid.uuid4()}"
    async with sesion_de_empresa(sesiones, empresa_a) as sesion:
        await _avisar(_caso(sesion, Canal(wamid)), empresa_a, cliente_a)

    async with sesion_de_empresa(sesiones, empresa_b) as sesion:
        assert await RepositorioConversacionPostgres(sesion).abierta_de(cliente_a) is None
        assert await RepositorioMensajePostgres(sesion).buscar_por_externo_id(wamid) is None
