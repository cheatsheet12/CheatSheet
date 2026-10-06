"""Waiting out Meta's verification (HU-E2-03 RN-02), on a schedule.

Two tasks, and the split is what keeps a cross-tenant sweep from becoming a cross-tenant
transaction:

- **`integrations.sondear_pendientes`** — the Beat entry. Asks which companies have
  something pending, through a `SECURITY DEFINER` function that returns nothing but ids,
  and fans out one message per company. It touches no aggregate and opens no company
  session.
- **`integrations.sondear_empresa`** — one company, one ordinary session, Row-Level
  Security applying exactly as it does for a request.

`conexion-arca` adds a second pair with the same shape and a different question:
**`integrations.revisar_vencimientos`** and **`integrations.revisar_empresa`**, which watch
a fiscal certificate's expiry date (HU-E2-01 RN-04). They run daily rather than every half
hour, because a `notAfter` moves once every two years — and they cost no call to ARCA, so
warning ahead of expiry is affordable.

`conexion-mercadopago` adds a third: **`integrations.renovar_credenciales`** and
**`integrations.renovar_empresa`** (HU-E2-02 RN-03). A third pair rather than a branch
inside the second, because the two differ where it matters — the ARCA sweep reads a date
that is already in our hands and calls nobody, while this one calls the provider and
**rewrites the stored credential**. Folding a credential write into a read-only sweep is
how a task that used to be safe to re-run stops being one.

**This module is also where `integrations` and `identity` meet, and that is deliberate.**
ADR-0003 makes `integrations` an Open Host Service with `identity` among its consumers, so
the context itself must not reach back into `identity` — the use case therefore takes the
recipients as an argument and this task, which is composition root, resolves them. Same
place and same licence `tasks_identity.py` already uses to compose `identity`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any
from uuid import UUID

from celery import Celery
from kombu.exceptions import KombuError
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.contexts.identity.application.usuarios import ListarUsuarios
from cheatsheet.contexts.identity.infrastructure.repositories import (
    RepositorioInvitacionPostgres,
    RepositorioUsuarioPostgres,
)
from cheatsheet.contexts.integrations.application.ports import AvisoDeIntegracion
from cheatsheet.contexts.integrations.application.renovacion import RenovarCredenciales
from cheatsheet.contexts.integrations.application.sondeo import (
    Desenlace,
    SondearIntegracionesPendientes,
)
from cheatsheet.contexts.integrations.application.vencimientos import RevisarVencimientos
from cheatsheet.contexts.integrations.infrastructure.ensamblado import Integraciones, crear_aviso
from cheatsheet.contexts.integrations.infrastructure.repositories import (
    empresas_con_integracion_de_arca,
    empresas_con_integracion_de_mercadopago,
    empresas_con_integracion_pendiente,
)
from cheatsheet.platform.database import sesion_sin_empresa
from cheatsheet.platform.settings import Settings
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.clock import RelojDelSistema
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.idempotencia import ClaveDeIdempotencia
from cheatsheet.shared.roles import RolUsuario
from cheatsheet.workers.base import EjecutorIdempotente, PoliticaDeReintentos
from cheatsheet.workers.celery_app import Cola, crear_celery
from cheatsheet.workers.ejecucion import ejecutar_tarea

logger = obtener_logger(__name__)

NOMBRE_BARRIDO = "integrations.sondear_pendientes"
NOMBRE_EMPRESA = "integrations.sondear_empresa"
NOMBRE_BARRIDO_VENCIMIENTOS = "integrations.revisar_vencimientos"
NOMBRE_EMPRESA_VENCIMIENTOS = "integrations.revisar_empresa"
NOMBRE_BARRIDO_RENOVACION = "integrations.renovar_credenciales"
NOMBRE_EMPRESA_RENOVACION = "integrations.renovar_empresa"

REINTENTOS = PoliticaDeReintentos()


async def sondear_pendientes(recursos: Recursos) -> int:
    """Fan out one message per company with something pending. Returns how many.

    Deliberately **not** idempotent: it reads and enqueues, and enqueuing the same company
    twice is already harmless because the per-company task claims an idempotency key. A
    key here would instead risk skipping a whole sweep after a redelivery.
    """
    async with sesion_sin_empresa(recursos.sesiones) as sesion:
        empresas = await empresas_con_integracion_pendiente(sesion)

    for empresa_id in empresas:
        _encolar_empresa(recursos.settings, empresa_id)
    logger.info("sondeo_de_integraciones_despachado", empresas=len(empresas))
    return len(empresas)


async def sondear_empresa(recursos: Recursos, empresa_id: EmpresaId, ventana: str) -> int:
    """Poll one company's pending integrations. Returns how many resolved.

    `ventana` is what makes the idempotency key change between scheduled runs while
    staying stable across a redelivery of the same one: two workers picking up the same
    message must not both ask Meta and both send the Administrator an email.
    """
    clave = ClaveDeIdempotencia.de(
        empresa_id=empresa_id, tipo=NOMBRE_EMPRESA, payload={"ventana": ventana}
    )

    async def efecto() -> int:
        desenlaces: list[Desenlace] = []
        destinatarios: tuple[str, ...] = ()
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Integraciones.armar(unidad.sesion, recursos.settings)
            desenlaces = await SondearIntegracionesPendientes(
                integraciones=piezas.integraciones,
                cifrado=piezas.cifrado,
                adaptadores=piezas.adaptadores,
                publicador=unidad.publicador,
                reloj=unidad.reloj,
                timeout_segundos=recursos.settings.whatsapp_timeout_segundos,
                maximo_dias=recursos.settings.whatsapp_sondeo_maximo_dias,
            ).ejecutar(empresa_id=empresa_id)
            if desenlaces:
                # Read inside the same transaction, and only when there is something to
                # say: the common outcome of a poll is "still pending", and that must not
                # cost a second query per company every thirty minutes.
                destinatarios = await _administradores(unidad.sesion, empresa_id)

        # Outside the transaction on purpose: a mail server that is slow must not hold a
        # database connection open, and the state change is already committed.
        await _avisar(recursos.settings, desenlaces, destinatarios)
        return len(desenlaces)

    return await EjecutorIdempotente(recursos.idempotencia()).ejecutar(clave, efecto) or 0


async def revisar_vencimientos(recursos: Recursos) -> int:
    """Fan out one message per company that has ARCA connected. Returns how many."""
    async with sesion_sin_empresa(recursos.sesiones) as sesion:
        empresas = await empresas_con_integracion_de_arca(sesion)

    for empresa_id in empresas:
        _encolar(
            recursos.settings, NOMBRE_EMPRESA_VENCIMIENTOS, empresa_id, _dia(recursos.settings)
        )
    logger.info("revision_de_vencimientos_despachada", empresas=len(empresas))
    return len(empresas)


async def revisar_empresa(recursos: Recursos, empresa_id: EmpresaId, ventana: str) -> int:
    """Check one company's dated credentials. Returns how many changed state.

    Same shape as `sondear_empresa`, deliberately: the two differ in the question they ask
    and in nothing else, so they are read side by side.
    """
    clave = ClaveDeIdempotencia.de(
        empresa_id=empresa_id, tipo=NOMBRE_EMPRESA_VENCIMIENTOS, payload={"ventana": ventana}
    )

    async def efecto() -> int:
        desenlaces: list[Desenlace] = []
        destinatarios: tuple[str, ...] = ()
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Integraciones.armar(unidad.sesion, recursos.settings)
            desenlaces = await RevisarVencimientos(
                integraciones=piezas.integraciones,
                cifrado=piezas.cifrado,
                adaptadores=piezas.adaptadores,
                publicador=unidad.publicador,
                reloj=unidad.reloj,
                timeout_segundos=recursos.settings.arca_timeout_segundos,
            ).ejecutar(empresa_id=empresa_id)
            if desenlaces:
                destinatarios = await _administradores(unidad.sesion, empresa_id)

        await _avisar(recursos.settings, desenlaces, destinatarios)
        return len(desenlaces)

    return await EjecutorIdempotente(recursos.idempotencia()).ejecutar(clave, efecto) or 0


async def renovar_credenciales(recursos: Recursos) -> int:
    """Fan out one message per company that has MercadoPago connected. Returns how many."""
    async with sesion_sin_empresa(recursos.sesiones) as sesion:
        empresas = await empresas_con_integracion_de_mercadopago(sesion)

    for empresa_id in empresas:
        _encolar(recursos.settings, NOMBRE_EMPRESA_RENOVACION, empresa_id, _dia(recursos.settings))
    logger.info("renovacion_de_credenciales_despachada", empresas=len(empresas))
    return len(empresas)


async def renovar_empresa(recursos: Recursos, empresa_id: EmpresaId, ventana: str) -> int:
    """Renew one company's OAuth credentials. Returns how many integrations went inactive.

    **Idempotent twice over.** The key makes a redelivery within the day a no-op, and even
    without it a second run finds nothing to do: the first renewal leaves the credential
    far from the margin. That belt-and-braces is deliberate — this task rewrites a stored
    credential, and MercadoPago rotates the refresh token on every exchange.
    """
    clave = ClaveDeIdempotencia.de(
        empresa_id=empresa_id, tipo=NOMBRE_EMPRESA_RENOVACION, payload={"ventana": ventana}
    )

    async def efecto() -> int:
        desenlaces: list[Desenlace] = []
        destinatarios: tuple[str, ...] = ()
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Integraciones.armar(unidad.sesion, recursos.settings)
            desenlaces = await RenovarCredenciales(
                integraciones=piezas.integraciones,
                cifrado=piezas.cifrado,
                adaptadores=piezas.adaptadores,
                publicador=unidad.publicador,
                reloj=unidad.reloj,
                margen_dias=recursos.settings.mercadopago_margen_renovacion_dias,
            ).ejecutar(empresa_id=empresa_id)
            if desenlaces:
                destinatarios = await _administradores(unidad.sesion, empresa_id)

        # Outside the transaction, like the other two: a slow mail server must not hold a
        # database connection open, and the state change is already committed.
        await _avisar(recursos.settings, desenlaces, destinatarios)
        return len(desenlaces)

    return await EjecutorIdempotente(recursos.idempotencia()).ejecutar(clave, efecto) or 0


async def _administradores(sesion: AsyncSession, empresa_id: EmpresaId) -> tuple[str, ...]:
    """The active administrators of one company (HU-E2-03: the Administrator is told).

    Reached through `identity`'s application service, never its domain or its tables —
    which is the rule R3 states and the reason this lives in `workers/` rather than inside
    `integrations`.
    """
    listado = await ListarUsuarios(
        usuarios=RepositorioUsuarioPostgres(sesion),
        invitaciones=RepositorioInvitacionPostgres(sesion),
    ).ejecutar(empresa_id=empresa_id)
    return tuple(
        str(fila.usuario.email)
        for fila in listado
        if fila.usuario.rol is RolUsuario.ADMINISTRADOR and fila.usuario.activo
    )


async def _avisar(
    settings: Settings, desenlaces: list[Desenlace], destinatarios: tuple[str, ...]
) -> None:
    if not desenlaces:
        return
    aviso = crear_aviso(settings)
    for desenlace in desenlaces:
        await aviso.avisar(
            AvisoDeIntegracion(
                destinatarios=destinatarios,
                sistema=desenlace.cambio.sistema,
                estado=desenlace.estado,
                detalle=desenlace.detalle,
            )
        )


@lru_cache(maxsize=1)
def _despachador(settings: Settings) -> Celery:
    """The sweep's Celery client, built once. `Settings` is frozen, so this caches."""
    return crear_celery(settings)


def _encolar_empresa(settings: Settings, empresa_id: EmpresaId) -> None:
    """Never breaks the sweep: one company that cannot be enqueued is retried in 30 min."""
    _encolar(settings, NOMBRE_EMPRESA, empresa_id, _ventana(settings))


def _encolar(settings: Settings, tarea: str, empresa_id: EmpresaId, ventana: str) -> None:
    """Enqueue one per-company message. A broker outage never breaks the sweep.

    Turning it into an exception would fail the whole fan-out over one company, which is
    exactly the failure mode splitting the sweep in two exists to avoid — the next run
    picks it up.
    """
    try:
        _despachador(settings).send_task(
            tarea,
            kwargs={"empresa_id": str(empresa_id), "ventana": ventana},
            queue=Cola.INTEGRATIONS_SYNC.value,
        )
    except (KombuError, OSError) as exc:
        logger.warning(
            "tarea_de_empresa_sin_encolar",
            tarea=tarea,
            empresa=str(empresa_id),
            tipo=type(exc).__name__,
        )


def _ventana(settings: Settings) -> str:
    """Names the scheduled run, so a redelivery shares a key and the next run does not.

    Derived from the clock rather than from a counter because the sweep holds no state and
    Beat may restart between runs.
    """
    minutos = max(settings.whatsapp_sondeo_minutos, 1)
    ahora = RelojDelSistema().ahora()
    marca = int(ahora.timestamp()) // (minutos * 60)
    return f"{minutos}m-{marca}"


def _dia(settings: Settings) -> str:
    """Names the daily run. Same purpose as `_ventana`, at a day's resolution.

    Derived from the clock rather than from a counter because Beat holds no state and may
    restart between runs.
    """
    del settings
    return f"dia-{RelojDelSistema().ahora().date().isoformat()}"


def registrar_en(app: Celery, settings: Settings) -> None:
    """Register both tasks on a worker's Celery application.

    Neither retries on a provider failure, and that is on purpose: `verificar_con_timeout`
    already turns an unreachable Meta into "no verdict", which leaves the integration
    pending and the next scheduled run asks again. Retrying here would ask three times
    within one window and change nothing.
    """

    # Celery ships no type information, so its decorator erases the signature it wraps.
    @app.task(  # type: ignore[misc]
        name=NOMBRE_BARRIDO,
        queue=Cola.INTEGRATIONS_SYNC.value,
        autoretry_for=(OSError,),
        retry_backoff=REINTENTOS.espera_base,
        retry_backoff_max=REINTENTOS.espera_maxima,
        retry_jitter=True,
        max_retries=REINTENTOS.max_intentos,
    )
    def _barrido() -> Any:
        return sondear_pendientes_sync(settings)

    @app.task(  # type: ignore[misc]
        name=NOMBRE_EMPRESA,
        queue=Cola.INTEGRATIONS_SYNC.value,
        autoretry_for=(OSError,),
        retry_backoff=REINTENTOS.espera_base,
        retry_backoff_max=REINTENTOS.espera_maxima,
        retry_jitter=True,
        max_retries=REINTENTOS.max_intentos,
    )
    def _empresa(**kwargs: str) -> Any:
        return sondear_empresa_sync(settings, **kwargs)

    @app.task(  # type: ignore[misc]
        name=NOMBRE_BARRIDO_VENCIMIENTOS,
        queue=Cola.INTEGRATIONS_SYNC.value,
        autoretry_for=(OSError,),
        retry_backoff=REINTENTOS.espera_base,
        retry_backoff_max=REINTENTOS.espera_maxima,
        retry_jitter=True,
        max_retries=REINTENTOS.max_intentos,
    )
    def _barrido_vencimientos() -> Any:
        return revisar_vencimientos_sync(settings)

    @app.task(  # type: ignore[misc]
        name=NOMBRE_EMPRESA_VENCIMIENTOS,
        queue=Cola.INTEGRATIONS_SYNC.value,
        autoretry_for=(OSError,),
        retry_backoff=REINTENTOS.espera_base,
        retry_backoff_max=REINTENTOS.espera_maxima,
        retry_jitter=True,
        max_retries=REINTENTOS.max_intentos,
    )
    def _empresa_vencimientos(**kwargs: str) -> Any:
        return revisar_empresa_sync(settings, **kwargs)

    @app.task(  # type: ignore[misc]
        name=NOMBRE_BARRIDO_RENOVACION,
        queue=Cola.INTEGRATIONS_SYNC.value,
        autoretry_for=(OSError,),
        retry_backoff=REINTENTOS.espera_base,
        retry_backoff_max=REINTENTOS.espera_maxima,
        retry_jitter=True,
        max_retries=REINTENTOS.max_intentos,
    )
    def _barrido_renovacion() -> Any:
        return renovar_credenciales_sync(settings)

    @app.task(  # type: ignore[misc]
        name=NOMBRE_EMPRESA_RENOVACION,
        queue=Cola.INTEGRATIONS_SYNC.value,
        autoretry_for=(OSError,),
        retry_backoff=REINTENTOS.espera_base,
        retry_backoff_max=REINTENTOS.espera_maxima,
        retry_jitter=True,
        max_retries=REINTENTOS.max_intentos,
    )
    def _empresa_renovacion(**kwargs: str) -> Any:
        return renovar_empresa_sync(settings, **kwargs)


def sondear_pendientes_sync(settings: Settings) -> Any:
    """Celery's bridge into the async world. One loop and one set of resources per run."""
    return ejecutar_tarea(settings, sondear_pendientes)


def sondear_empresa_sync(settings: Settings, empresa_id: str, ventana: str) -> Any:
    return ejecutar_tarea(
        settings,
        lambda recursos: sondear_empresa(recursos, EmpresaId(UUID(empresa_id)), ventana),
    )


def revisar_vencimientos_sync(settings: Settings) -> Any:
    return ejecutar_tarea(settings, revisar_vencimientos)


def revisar_empresa_sync(settings: Settings, empresa_id: str, ventana: str) -> Any:
    return ejecutar_tarea(
        settings,
        lambda recursos: revisar_empresa(recursos, EmpresaId(UUID(empresa_id)), ventana),
    )


def renovar_credenciales_sync(settings: Settings) -> Any:
    return ejecutar_tarea(settings, renovar_credenciales)


def renovar_empresa_sync(settings: Settings, empresa_id: str, ventana: str) -> Any:
    return ejecutar_tarea(
        settings,
        lambda recursos: renovar_empresa(recursos, EmpresaId(UUID(empresa_id)), ventana),
    )
