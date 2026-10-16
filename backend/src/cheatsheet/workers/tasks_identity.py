"""Sending the invitation email (HU-E1-04 RN-02).

**Why this is a task and not an inline call.** A mail server that is slow makes the invite
request slow; one that is down makes it fail — after the invitation row has already been
committed. Neither is acceptable on a screen where the administrator's next move depends
on seeing the row appear. So the endpoint commits, enqueues, and answers; the queue owns
the retry.

**The failure mode is chosen deliberately.** If every attempt fails, the invitation stays
created and pending, and the administrator can resend it (RN-04). Losing the invitation
because SMTP coughed would be worse than a late email — and worse than an error on a
request whose actual work succeeded, which is why `encolar_invitacion` swallows a broker
outage instead of turning it into a 500.

**The token travels in the task's arguments and lives nowhere else.** Only its hash is in
the database, so this payload is the last copy. That is also why nothing here logs it: a
live invitation link in an aggregated log is an account waiting to be taken.
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Any
from uuid import UUID

from celery import Celery
from kombu.exceptions import KombuError

from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.contexts.identity.application.errors import EnvioDeEmailFallido
from cheatsheet.contexts.identity.application.ports import MensajeDeInvitacion
from cheatsheet.contexts.identity.domain.valores import Email
from cheatsheet.contexts.identity.infrastructure.ensamblado import crear_enviador
from cheatsheet.contexts.identity.infrastructure.repositories import (
    RepositorioEmpresaPostgres,
    RepositorioUsuarioPostgres,
)
from cheatsheet.platform.settings import Settings
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.idempotencia import ClaveDeIdempotencia
from cheatsheet.workers.base import AnteUnaFalla, EjecutorIdempotente, PoliticaDeReintentos
from cheatsheet.workers.celery_app import Cola, crear_celery
from cheatsheet.workers.ejecucion import ejecutar_tarea

logger = obtener_logger(__name__)

NOMBRE = "identity.enviar_invitacion"

#: Fallback when the company has not filled in its `razon_social` yet — the first
#: administrator can invite people during the onboarding, before step 2.
EMPRESA_SIN_NOMBRE = "tu empresa"

REINTENTOS = PoliticaDeReintentos()


async def enviar_invitacion(
    recursos: Recursos,
    *,
    empresa_id: EmpresaId,
    invitacion_id: UUID,
    destinatario: str,
    invitado_por_id: UsuarioId,
    token: str,
    expira_en: datetime,
) -> bool:
    """Send one invitation. Returns False if this exact one was already sent.

    Idempotent on the invitation **and its expiry**: a Celery redelivery of the same
    message must not put a second email in somebody's inbox. Resending mints a new token
    with a new expiry, so it produces a different key and is correctly allowed through.
    """
    clave = ClaveDeIdempotencia.de(
        empresa_id=empresa_id,
        tipo=NOMBRE,
        payload={"invitacion_id": str(invitacion_id), "expira_en": expira_en.isoformat()},
    )

    async def efecto() -> bool:
        nombre_empresa, quien_invita = await _contexto(recursos, empresa_id, invitado_por_id)
        await crear_enviador(recursos.settings).enviar_invitacion(
            MensajeDeInvitacion(
                destinatario=Email(destinatario),
                nombre_de_empresa=nombre_empresa,
                invitado_por=quien_invita,
                token=token,
                expira_en=expira_en,
            )
        )
        return True

    # LIBERAR: if the sender raised, the mail did not go out, and `autoretry_for` must be
    # able to send it. The residual risk is a mail accepted by the server whose reply
    # was lost: the invitee may then get two, and the second link is as valid as the first.
    enviado = await EjecutorIdempotente(recursos.idempotencia()).ejecutar(
        clave, efecto, ante_una_falla=AnteUnaFalla.LIBERAR
    )
    return bool(enviado)


async def _contexto(
    recursos: Recursos, empresa_id: EmpresaId, invitado_por_id: UsuarioId
) -> tuple[str, str]:
    """The two names the email shows, read in a transaction this task owns."""
    nombre_empresa = EMPRESA_SIN_NOMBRE
    quien_invita = "Un administrador"
    async for unidad in unidad_de_trabajo(recursos, empresa_id):
        empresa = await RepositorioEmpresaPostgres(unidad.sesion).buscar_por_id(empresa_id)
        if empresa is not None and empresa.razon_social:
            nombre_empresa = empresa.razon_social
        quien = await RepositorioUsuarioPostgres(unidad.sesion).buscar_por_id(invitado_por_id)
        if quien is not None:
            quien_invita = quien.nombre
    return nombre_empresa, quien_invita


@lru_cache(maxsize=1)
def _despachador(settings: Settings) -> Celery:
    """The API process's Celery client, built once.

    `Settings` is a frozen dataclass of scalars, so it is hashable and this caches
    cleanly. Constructing the application opens no connection — the first `send_task`
    does.
    """
    return crear_celery(settings)


async def encolar_invitacion(
    recursos: Recursos,
    *,
    empresa_id: EmpresaId,
    invitacion_id: UUID,
    destinatario: str,
    invitado_por_id: UsuarioId,
    token: str,
    expira_en: datetime,
) -> None:
    """Put the send on the `notifications` queue. Never breaks the request.

    The invitation is already committed by the time this runs, so a broker that is
    unreachable must not turn a successful operation into a 500: the administrator sees
    the pending row and can resend it.
    """
    try:
        _despachador(recursos.settings).send_task(
            NOMBRE,
            kwargs={
                "empresa_id": str(empresa_id),
                "invitacion_id": str(invitacion_id),
                "destinatario": destinatario,
                "invitado_por_id": str(invitado_por_id),
                "token": token,
                "expira_en": expira_en.isoformat(),
            },
            queue=Cola.NOTIFICATIONS.value,
        )
    except (KombuError, OSError) as exc:
        logger.warning(
            "invitacion_creada_sin_encolar",
            invitacion_id=str(invitacion_id),
            tipo=type(exc).__name__,
        )


def registrar_en(app: Celery, settings: Settings) -> None:
    """Register the task on a worker's Celery application.

    Takes `Settings`, not `Recursos`: each execution builds its own inside its own event
    loop (see `workers/ejecucion.py`). Holding an engine across executions is what made
    the second invitation of every worker fail.

    `autoretry_for` covers the two failures worth retrying — the mail server refused, or
    the socket did — with the exponential backoff and jitter of ADR-009. A
    `ConfiguracionFaltante` or a malformed address is not retried: it would fail
    identically five more times.
    """

    # Celery ships no type information, so its decorator erases the signature it wraps.
    # The function below is fully annotated; only the decorator is opaque.
    @app.task(  # type: ignore[misc]
        name=NOMBRE,
        queue=Cola.NOTIFICATIONS.value,
        autoretry_for=(EnvioDeEmailFallido, OSError),
        retry_backoff=REINTENTOS.espera_base,
        retry_backoff_max=REINTENTOS.espera_maxima,
        retry_jitter=True,
        max_retries=REINTENTOS.max_intentos,
    )
    def _tarea(**kwargs: str) -> Any:
        return enviar_invitacion_sync(settings, **kwargs)


def enviar_invitacion_sync(
    settings: Settings,
    empresa_id: str,
    invitacion_id: str,
    destinatario: str,
    invitado_por_id: str,
    token: str,
    expira_en: str,
) -> Any:
    """Celery's bridge into the async world, same shape as `tasks.registrar_latido_sync`."""
    return ejecutar_tarea(
        settings,
        lambda recursos: enviar_invitacion(
            recursos,
            empresa_id=EmpresaId(UUID(empresa_id)),
            invitacion_id=UUID(invitacion_id),
            destinatario=destinatario,
            invitado_por_id=UsuarioId(UUID(invitado_por_id)),
            token=token,
            expira_en=datetime.fromisoformat(expira_en),
        ),
    )
