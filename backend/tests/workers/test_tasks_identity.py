"""The invitation-sending task (HU-E1-04 RN-02).

Cases 29 and 30 of the plan. The task's two jobs are *not* sending an email — the adapter
does that, and its own test covers it. They are: sending it **once** even though the queue
promises at-least-once delivery, and never letting a broker outage undo an invitation that
is already committed.

`_contexto` reads two names from the database. It is stubbed here: what this file is about
is the guarantee around the send, not the query that decorates it.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, cast
from uuid import uuid4

import pytest
from cheatsheet.api.dependencies import Recursos
from cheatsheet.contexts.identity.application.errors import EnvioDeEmailFallido
from cheatsheet.contexts.identity.application.ports import MensajeDeInvitacion
from cheatsheet.platform.cache import RegistroDeIdempotenciaEnMemoria
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.workers import tasks_identity
from kombu.exceptions import OperationalError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.conftest import INSTANTE_FIJO

pytestmark = pytest.mark.asyncio

TOKEN = "un-token-de-invitacion-de-prueba"
VENCE = INSTANTE_FIJO + timedelta(days=7)
EMPRESA = EmpresaId(uuid4())


class EnviadorEspia:
    def __init__(self, *, falla: bool = False) -> None:
        self.enviados: list[MensajeDeInvitacion] = []
        self._falla = falla

    async def enviar_invitacion(self, mensaje: MensajeDeInvitacion) -> None:
        if self._falla:
            raise EnvioDeEmailFallido("El servidor de correo no respondio")
        self.enviados.append(mensaje)


def _recursos(settings: Any) -> Recursos:
    """Engine and Redis are never dereferenced: the registry and the sender are stubbed."""
    return Recursos(
        settings=settings,
        engine=cast(AsyncEngine, None),
        sesiones=cast("async_sessionmaker[AsyncSession]", None),
        redis=cast(Redis, None),
        reloj=RelojFijo(INSTANTE_FIJO),
    )


@pytest.fixture
def entorno(monkeypatch, settings):
    """One in-memory idempotency registry and one spy, wired into the module."""
    registro = RegistroDeIdempotenciaEnMemoria()
    enviador = EnviadorEspia()
    monkeypatch.setattr(Recursos, "idempotencia", lambda _recursos: registro)
    monkeypatch.setattr(tasks_identity, "crear_enviador", lambda _settings: enviador)

    async def contexto_falso(*args: object, **kwargs: object) -> tuple[str, str]:
        return "Panaderia Dona Rosa", "Ana Perez"

    monkeypatch.setattr(tasks_identity, "_contexto", contexto_falso)
    return _recursos(settings), enviador


async def _enviar(recursos: Recursos, *, invitacion_id, expira_en=VENCE, empresa_id=None) -> bool:
    # The idempotency key is scoped by company, so a test that meant to repeat one send
    # has to repeat the company too.
    return await tasks_identity.enviar_invitacion(
        recursos,
        empresa_id=empresa_id or EMPRESA,
        invitacion_id=invitacion_id,
        destinatario="nuevo@empresa.com",
        invitado_por_id=UsuarioId(uuid4()),
        token=TOKEN,
        expira_en=expira_en,
    )


async def test_dos_ejecuciones_de_la_misma_tarea_mandan_un_solo_mail(entorno):
    """Caso 30. At-least-once delivery is all a queue can promise, so the second run has
    to be a no-op — nobody gets the same invitation twice."""
    recursos, enviador = entorno
    invitacion_id = uuid4()

    primera = await _enviar(recursos, invitacion_id=invitacion_id)
    segunda = await _enviar(recursos, invitacion_id=invitacion_id)

    assert primera is True
    assert segunda is False
    assert len(enviador.enviados) == 1


async def test_un_reenvio_si_manda_un_mail_nuevo(entorno):
    """Resending mints a new token with a new expiry, so it is a different key — and
    RN-04 says the administrator may resend."""
    recursos, enviador = entorno
    invitacion_id = uuid4()
    await _enviar(recursos, invitacion_id=invitacion_id)

    await _enviar(recursos, invitacion_id=invitacion_id, expira_en=VENCE + timedelta(days=1))

    assert len(enviador.enviados) == 2


async def test_el_mensaje_lleva_el_token_y_el_nombre_de_la_empresa(entorno):
    recursos, enviador = entorno

    await _enviar(recursos, invitacion_id=uuid4())

    mensaje = enviador.enviados[0]
    assert mensaje.token == TOKEN
    assert mensaje.nombre_de_empresa == "Panaderia Dona Rosa"
    assert mensaje.invitado_por == "Ana Perez"
    assert str(mensaje.destinatario) == "nuevo@empresa.com"


async def test_si_el_correo_falla_el_error_sube_para_que_celery_reintente(monkeypatch, settings):
    """Caso 29, first half: the task must not swallow it, or the retry never happens."""
    monkeypatch.setattr(
        Recursos, "idempotencia", lambda _recursos: RegistroDeIdempotenciaEnMemoria()
    )
    monkeypatch.setattr(tasks_identity, "crear_enviador", lambda _s: EnviadorEspia(falla=True))

    async def contexto_falso(*args: object, **kwargs: object) -> tuple[str, str]:
        return "Panaderia Dona Rosa", "Ana Perez"

    monkeypatch.setattr(tasks_identity, "_contexto", contexto_falso)

    with pytest.raises(EnvioDeEmailFallido):
        await _enviar(_recursos(settings), invitacion_id=uuid4())


async def test_un_broker_caido_no_rompe_la_invitacion_ya_creada(monkeypatch, settings):
    """Caso 29, second half. The row is already committed: turning this into a 500 would
    report a failure for work that succeeded, and the administrator can resend."""

    class DespachadorCaido:
        def send_task(self, *_args: object, **_kwargs: object) -> None:
            raise OperationalError("no hay broker")

    monkeypatch.setattr(tasks_identity, "_despachador", lambda _s: DespachadorCaido())

    await tasks_identity.encolar_invitacion(
        _recursos(settings),
        empresa_id=EmpresaId(uuid4()),
        invitacion_id=uuid4(),
        destinatario="nuevo@empresa.com",
        invitado_por_id=UsuarioId(uuid4()),
        token=TOKEN,
        expira_en=VENCE,
    )


async def test_encolar_manda_a_la_cola_de_notificaciones(monkeypatch, settings):
    """ADR-003: the queue is part of the contract, not an implementation detail."""
    enviadas: list[dict[str, Any]] = []

    class DespachadorEspia:
        def send_task(self, nombre: str, **kwargs: Any) -> None:
            enviadas.append({"nombre": nombre, **kwargs})

    monkeypatch.setattr(tasks_identity, "_despachador", lambda _s: DespachadorEspia())

    await tasks_identity.encolar_invitacion(
        _recursos(settings),
        empresa_id=EmpresaId(uuid4()),
        invitacion_id=uuid4(),
        destinatario="nuevo@empresa.com",
        invitado_por_id=UsuarioId(uuid4()),
        token=TOKEN,
        expira_en=VENCE,
    )

    assert enviadas[0]["nombre"] == tasks_identity.NOMBRE
    assert enviadas[0]["queue"] == "notifications"
    # The clear-text token travels here and nowhere else — the database holds only its hash.
    assert enviadas[0]["kwargs"]["token"] == TOKEN
