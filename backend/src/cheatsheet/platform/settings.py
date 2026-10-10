"""Typed configuration, read once from the environment.

Two rules shape this module:

1. **No default for anything that is a secret or an address.** A `DATABASE_URL` that
   falls back to localhost is how a staging job quietly writes to a developer's
   laptop, and how a missing variable is discovered in production instead of at boot.
   Missing means the process does not start, with a message naming the variable.
2. **No pydantic here.** `platform/` is the floor everything else stands on; keeping
   it to the standard library means settings can be constructed in a test, in a
   migration and in a Celery worker without dragging a validation framework into
   places that only need three strings.

Real values travel over a private encrypted channel, never through the repository
(docs/configuration-management.md §4.3).
"""

from __future__ import annotations

import base64
import os
import re
from dataclasses import dataclass
from enum import StrEnum

from cheatsheet.platform.intervalos import IntervaloNoAlineable, campos_alineados

#: Default retry ceiling the DLQ sweep judges against (HS-T6 RN-01).
#:
#: Deliberately a literal and not an import of `workers.base.MAX_INTENTOS_POR_DEFECTO`:
#: `platform/` is the floor every other layer stands on, and importing a worker into it
#: would invert that. The two constants must agree — retiring tasks on a different
#: ceiling than the one they were retried under means they are retired either too early
#: or never — so a test asserts they are equal.
DLQ_MAX_INTENTOS_POR_DEFECTO = 5

#: The model ADR-0007 chose. A default and not a constant in the code: `LLM_MODELO`
#: overrides it, so trying a different one is a deployment change and not a release.
MODELO_POR_DEFECTO = "claude-opus-5"


class Entorno(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class AdaptadorDeEmail(StrEnum):
    """Which implementation of `PortEnvioDeEmail` gets wired.

    `CONSOLA` writes the invitation link to the log instead of sending it, so the flow is
    completable on a laptop with no mail server. `Settings` refuses it in production —
    see `desde_entorno`.
    """

    SMTP = "smtp"
    CONSOLA = "consola"


class AdaptadorDeWhatsApp(StrEnum):
    """Which implementation answers for WhatsApp Business (HU-E2-03).

    `SIMULADO` fabricates Meta's payloads and runs them through the real Anti-Corruption
    Layer, so the whole flow is completable on a laptop with no Meta app. It is
    **rejected in production** — see `desde_entorno` — for the same reason
    `EMAIL_ADAPTADOR=consola` is: a company would believe its number is connected while
    nothing has ever reached Meta.
    """

    META = "meta"
    SIMULADO = "simulado"


class AdaptadorDeArca(StrEnum):
    """Which implementation answers for ARCA (HU-E2-01).

    `SIMULADO` reuses the real credential parsing and the real expiry mapping and replaces
    only the network call. **Rejected in production**, and here that guard matters more
    than anywhere else in the system: a company believing it is connected to ARCA when
    nothing ever reached ARCA is a company that believes it can invoice.
    """

    ARCA = "arca"
    SIMULADO = "simulado"


class AdaptadorDeMercadoPago(StrEnum):
    """Which implementation answers for MercadoPago (HU-E2-02).

    `SIMULADO` walks the whole OAuth2 round trip — redirect included — and runs the
    fabricated payloads through the real Anti-Corruption Layer, so the flow is completable
    on a laptop with no sandbox application. **Rejected in production**: a company
    believing its account is connected when nothing ever reached MercadoPago is a company
    that believes it can charge.
    """

    MERCADOPAGO = "mercadopago"
    SIMULADO = "simulado"


class AdaptadorDePlanilla(StrEnum):
    """Which implementation answers for Google Sheets (HU-E2-04).

    `SIMULADO` walks the whole OAuth2 round trip against our own callback and returns a
    fabricated workbook through the real Anti-Corruption Layer. **Rejected in production**,
    like the three adapters of epic 2: a company believing its spreadsheet is linked when
    nothing ever reached Google is a company whose catalogue will never fill.
    """

    GOOGLE = "google"
    SIMULADO = "simulado"


class AdaptadorDeAlmacenamiento(StrEnum):
    """Where uploaded workbooks go.

    `MEMORIA` keeps them in the process. It is enough to upload a file and map it, and
    **not** enough to process one: RN-01 makes processing asynchronous, so the bytes are
    read by a Celery worker, and a worker is a different process with a different dict.
    The flow dead-ends at `planilla_sin_archivo_para_procesar`.

    `DISCO` is what makes the local promise true -- one directory both processes can read,
    no bucket, no credentials. Both are **rejected in production** for the same reason:
    the files would vanish on the next restart or deploy, silently.
    """

    R2 = "r2"
    MEMORIA = "memoria"
    DISCO = "disco"


class AdaptadorDeCatalogos(StrEnum):
    """Which implementation answers for ARCA's fiscal catalogue (HS-T4, ADR-0008).

    `SIMULADO` returns ARCA's **real** codes, hard-coded. Real ones on purpose: a simulator
    with invented codes would let the issuing code pass tests it would fail against ARCA,
    which is the one thing a fiscal simulator must not do. **Rejected in production**: a
    company invoicing against a snapshot is validating against what ARCA said the day the
    file was written.
    """

    WSFE = "wsfe"
    SIMULADO = "simulado"


class AdaptadorDeModelo(StrEnum):
    """Which implementation answers for the LLM (ADR-0007).

    `SIMULADO` maps headers by string similarity and opens no socket, so the ingestion flow
    is walkable on a laptop with no API key and no test ever touches the network.
    **Rejected in production**: a company whose mapping was guessed by string distance gets
    a catalogue that looks plausible and is wrong.
    """

    ANTHROPIC = "anthropic"
    SIMULADO = "simulado"


class ConfiguracionFaltante(RuntimeError):
    """A required environment variable is absent. Raised at boot, never later."""


def _requerida(nombre: str) -> str:
    valor = os.environ.get(nombre, "").strip()
    if not valor:
        raise ConfiguracionFaltante(
            f"Falta la variable de entorno {nombre}. "
            f"Copiá backend/.env.example y completala antes de arrancar."
        )
    return valor


def _opcional(nombre: str, por_defecto: str) -> str:
    return os.environ.get(nombre, "").strip() or por_defecto


def _booleano(nombre: str, por_defecto: bool) -> bool:
    crudo = os.environ.get(nombre, "").strip().lower()
    if not crudo:
        return por_defecto
    return crudo in {"1", "true", "yes", "si"}


def _intervalo_en_minutos(nombre: str, por_defecto: int) -> int:
    """An interval Beat anchors to the wall clock; one that cannot be anchored fails at boot."""
    valor = _entero(nombre, por_defecto)
    try:
        campos_alineados(valor)
    except IntervaloNoAlineable as exc:
        raise ConfiguracionFaltante(f"{nombre}: {exc}") from exc
    return valor


def _intervalo_en_horas(nombre: str, por_defecto: int) -> int:
    """Hours variant of `_intervalo_en_minutos`: the same rule, applied to hours x 60."""
    valor = _entero(nombre, por_defecto)
    try:
        campos_alineados(valor * 60)
    except IntervaloNoAlineable as exc:
        raise ConfiguracionFaltante(
            f"{nombre}: {valor} hours does not divide a day exactly; use 1, 2, 3, 4, 6, 8, 12 or 24"
        ) from exc
    return valor


def _entero(nombre: str, por_defecto: int) -> int:
    crudo = os.environ.get(nombre, "").strip()
    if not crudo:
        return por_defecto
    try:
        return int(crudo)
    except ValueError as exc:
        raise ConfiguracionFaltante(f"{nombre} debe ser un numero entero, no '{crudo}'") from exc


def _adaptador_de_catalogos(entorno: Entorno) -> AdaptadorDeCatalogos:
    """Defaults to the simulator outside production, and is forbidden inside it."""
    crudo = _opcional("CATALOGOS_FISCALES_ADAPTADOR", "")
    if not crudo:
        if entorno is Entorno.PRODUCTION:
            raise ConfiguracionFaltante(
                "Falta la variable de entorno CATALOGOS_FISCALES_ADAPTADOR. "
                "En produccion debe valer 'wsfe'."
            )
        return AdaptadorDeCatalogos.SIMULADO
    try:
        adaptador = AdaptadorDeCatalogos(crudo)
    except ValueError as exc:
        raise ConfiguracionFaltante(
            f"CATALOGOS_FISCALES_ADAPTADOR debe ser 'wsfe' o 'simulado', no '{crudo}'"
        ) from exc
    if adaptador is AdaptadorDeCatalogos.SIMULADO and entorno is Entorno.PRODUCTION:
        raise ConfiguracionFaltante(
            "CATALOGOS_FISCALES_ADAPTADOR=simulado no es valido en produccion: "
            "los comprobantes se validarian contra una foto y no contra ARCA."
        )
    return adaptador


def _adaptador_de_modelo(entorno: Entorno) -> AdaptadorDeModelo:
    """Defaults to the simulator outside production, and is forbidden inside it."""
    crudo = _opcional("LLM_ADAPTADOR", "")
    if not crudo:
        if entorno is Entorno.PRODUCTION:
            raise ConfiguracionFaltante(
                "Falta la variable de entorno LLM_ADAPTADOR. En produccion debe valer 'anthropic'."
            )
        return AdaptadorDeModelo.SIMULADO
    try:
        adaptador = AdaptadorDeModelo(crudo)
    except ValueError as exc:
        raise ConfiguracionFaltante(
            f"LLM_ADAPTADOR debe ser 'anthropic' o 'simulado', no '{crudo}'"
        ) from exc
    if adaptador is AdaptadorDeModelo.SIMULADO and entorno is Entorno.PRODUCTION:
        raise ConfiguracionFaltante(
            "LLM_ADAPTADOR=simulado no es valido en produccion: "
            "el mapeo de columnas se adivinaria por parecido de texto."
        )
    return adaptador


def _adaptador_de_planilla(entorno: Entorno) -> AdaptadorDePlanilla:
    """Defaults to the simulator outside production, and is forbidden inside it."""
    crudo = _opcional("PLANILLA_ADAPTADOR", "")
    if not crudo:
        if entorno is Entorno.PRODUCTION:
            raise ConfiguracionFaltante(
                "Falta la variable de entorno PLANILLA_ADAPTADOR. En produccion debe valer 'google'."
            )
        return AdaptadorDePlanilla.SIMULADO
    try:
        adaptador = AdaptadorDePlanilla(crudo)
    except ValueError as exc:
        raise ConfiguracionFaltante(
            f"PLANILLA_ADAPTADOR debe ser 'google' o 'simulado', no '{crudo}'"
        ) from exc
    if adaptador is AdaptadorDePlanilla.SIMULADO and entorno is Entorno.PRODUCTION:
        raise ConfiguracionFaltante(
            "PLANILLA_ADAPTADOR=simulado no es valido en produccion: "
            "ninguna planilla llegaria a vincularse."
        )
    return adaptador


def _adaptador_de_almacenamiento(entorno: Entorno) -> AdaptadorDeAlmacenamiento:
    """Defaults to memory outside production, and is forbidden inside it."""
    crudo = _opcional("ALMACENAMIENTO_ADAPTADOR", "")
    if not crudo:
        if entorno is Entorno.PRODUCTION:
            raise ConfiguracionFaltante(
                "Falta la variable de entorno ALMACENAMIENTO_ADAPTADOR. "
                "En produccion debe valer 'r2'."
            )
        return AdaptadorDeAlmacenamiento.MEMORIA
    try:
        adaptador = AdaptadorDeAlmacenamiento(crudo)
    except ValueError as exc:
        raise ConfiguracionFaltante(
            f"ALMACENAMIENTO_ADAPTADOR debe ser 'r2', 'memoria' o 'disco', no '{crudo}'"
        ) from exc
    if adaptador is not AdaptadorDeAlmacenamiento.R2 and entorno is Entorno.PRODUCTION:
        raise ConfiguracionFaltante(
            f"ALMACENAMIENTO_ADAPTADOR={adaptador.value} no es valido en produccion: "
            "las planillas subidas se perderian al reiniciar el proceso."
        )
    return adaptador


def _adaptador_de_email(entorno: Entorno) -> AdaptadorDeEmail:
    """Defaults to the console outside production, and is forbidden inside it.

    An invitation that silently goes to a log file instead of to a person is the kind of
    misconfiguration nobody notices until somebody asks why they never got their email.
    In production the variable has to say `smtp`, or the process does not start.
    """
    crudo = _opcional("EMAIL_ADAPTADOR", "")
    if not crudo:
        if entorno is Entorno.PRODUCTION:
            raise ConfiguracionFaltante(
                "Falta la variable de entorno EMAIL_ADAPTADOR. En produccion debe valer 'smtp'."
            )
        return AdaptadorDeEmail.CONSOLA
    try:
        adaptador = AdaptadorDeEmail(crudo)
    except ValueError as exc:
        raise ConfiguracionFaltante(
            f"EMAIL_ADAPTADOR debe ser 'smtp' o 'consola', no '{crudo}'"
        ) from exc
    if adaptador is AdaptadorDeEmail.CONSOLA and entorno is Entorno.PRODUCTION:
        raise ConfiguracionFaltante(
            "EMAIL_ADAPTADOR=consola no es valido en produccion: "
            "las invitaciones quedarian sin enviar."
        )
    return adaptador


def _adaptador_de_whatsapp(entorno: Entorno) -> AdaptadorDeWhatsApp:
    """Defaults to the simulator outside production, and is forbidden inside it."""
    crudo = _opcional("WHATSAPP_ADAPTADOR", "")
    if not crudo:
        if entorno is Entorno.PRODUCTION:
            raise ConfiguracionFaltante(
                "Falta la variable de entorno WHATSAPP_ADAPTADOR. En produccion debe valer 'meta'."
            )
        return AdaptadorDeWhatsApp.SIMULADO
    try:
        adaptador = AdaptadorDeWhatsApp(crudo)
    except ValueError as exc:
        raise ConfiguracionFaltante(
            f"WHATSAPP_ADAPTADOR debe ser 'meta' o 'simulado', no '{crudo}'"
        ) from exc
    if adaptador is AdaptadorDeWhatsApp.SIMULADO and entorno is Entorno.PRODUCTION:
        raise ConfiguracionFaltante(
            "WHATSAPP_ADAPTADOR=simulado no es valido en produccion: "
            "ninguna verificacion llegaria a Meta."
        )
    return adaptador


#: The end of one PEM block glued to the start of the next.
_JUNTURA_PEM = re.compile(rb"-----(?=-----BEGIN )")


def _credencial_de_plataforma(adaptador: AdaptadorDeArca) -> bytes:
    """`ARCA_CREDENCIAL_PLATAFORMA`: base64 of the PEM certificate plus its PEM key (ADR-0014).

    Required as soon as ARCA is real: without it no company can be reached. Base64 because
    a PEM bundle is several lines, and an environment variable is one.
    """
    if adaptador is not AdaptadorDeArca.ARCA:
        return b""
    crudo = _requerida("ARCA_CREDENCIAL_PLATAFORMA")
    try:
        bundle = base64.b64decode(crudo, validate=True)
    except (ValueError, TypeError) as exc:
        raise ConfiguracionFaltante(
            "ARCA_CREDENCIAL_PLATAFORMA debe ser el certificado y la clave PEM en base64"
        ) from exc
    # The certificate WSASS hands out ends without a newline, so `cat crt key` glues
    # `-----END CERTIFICATE-----` to `-----BEGIN PRIVATE KEY-----` and the key no longer
    # parses -- with an error that blames the key. Found on 2026-10-10 with the real one.
    return _JUNTURA_PEM.sub(b"-----\n", bundle)


def _adaptador_del_padron(entorno: Entorno, arca: AdaptadorDeArca) -> AdaptadorDeArca:
    """`ARCA_PADRON_ADAPTADOR`: defaults to whatever ARCA is, and is never simulated in
    production — a company validated against an invented registry would invoice on the
    strength of a fiscal condition nobody checked."""
    crudo = _opcional("ARCA_PADRON_ADAPTADOR", "")
    if not crudo:
        return arca
    try:
        adaptador = AdaptadorDeArca(crudo)
    except ValueError as exc:
        raise ConfiguracionFaltante(
            f"ARCA_PADRON_ADAPTADOR debe ser 'arca' o 'simulado', no '{crudo}'"
        ) from exc
    if adaptador is AdaptadorDeArca.SIMULADO and entorno is Entorno.PRODUCTION:
        raise ConfiguracionFaltante(
            "ARCA_PADRON_ADAPTADOR=simulado no es valido en produccion: el padron tiene que ser el de ARCA."
        )
    return adaptador


def _adaptador_de_arca(entorno: Entorno) -> AdaptadorDeArca:
    """Defaults to the simulator outside production, and is forbidden inside it."""
    crudo = _opcional("ARCA_ADAPTADOR", "")
    if not crudo:
        if entorno is Entorno.PRODUCTION:
            raise ConfiguracionFaltante(
                "Falta la variable de entorno ARCA_ADAPTADOR. En produccion debe valer 'arca'."
            )
        return AdaptadorDeArca.SIMULADO
    try:
        adaptador = AdaptadorDeArca(crudo)
    except ValueError as exc:
        raise ConfiguracionFaltante(
            f"ARCA_ADAPTADOR debe ser 'arca' o 'simulado', no '{crudo}'"
        ) from exc
    if adaptador is AdaptadorDeArca.SIMULADO and entorno is Entorno.PRODUCTION:
        raise ConfiguracionFaltante(
            "ARCA_ADAPTADOR=simulado no es valido en produccion: "
            "ninguna credencial fiscal se validaria contra ARCA."
        )
    return adaptador


def _url_de_notificaciones(adaptador: AdaptadorDeMercadoPago) -> str:
    """`API_URL_PUBLICA`, required as soon as MercadoPago is real.

    Every payment link carries it as `notification_url`. The application-level webhook in
    MercadoPago cannot replace it: it is a single URL, and ours needs the company in the path.
    """
    if adaptador is AdaptadorDeMercadoPago.MERCADOPAGO:
        return _requerida("API_URL_PUBLICA").rstrip("/")
    return _opcional("API_URL_PUBLICA", "").rstrip("/")


def _adaptador_de_mercadopago(entorno: Entorno) -> AdaptadorDeMercadoPago:
    """Defaults to the simulator outside production, and is forbidden inside it."""
    crudo = _opcional("MERCADOPAGO_ADAPTADOR", "")
    if not crudo:
        if entorno is Entorno.PRODUCTION:
            raise ConfiguracionFaltante(
                "Falta la variable de entorno MERCADOPAGO_ADAPTADOR. "
                "En produccion debe valer 'mercadopago'."
            )
        return AdaptadorDeMercadoPago.SIMULADO
    try:
        adaptador = AdaptadorDeMercadoPago(crudo)
    except ValueError as exc:
        raise ConfiguracionFaltante(
            f"MERCADOPAGO_ADAPTADOR debe ser 'mercadopago' o 'simulado', no '{crudo}'"
        ) from exc
    if adaptador is AdaptadorDeMercadoPago.SIMULADO and entorno is Entorno.PRODUCTION:
        raise ConfiguracionFaltante(
            "MERCADOPAGO_ADAPTADOR=simulado no es valido en produccion: "
            "ninguna cuenta se conectaria de verdad."
        )
    return adaptador


@dataclass(frozen=True, slots=True)
class Settings:
    """Everything the backend needs to know about where it is running."""

    entorno: Entorno
    database_url: str
    database_url_migrations: str
    redis_url: str
    celery_broker_url: str
    celery_result_backend: str
    log_level: str
    jwt_secret: str
    jwt_access_ttl_minutos: int
    refresh_ttl_dias: int
    terminos_version_vigente: str
    google_oauth_client_id: str
    google_oauth_client_secret: str
    google_oauth_redirect_uri: str
    app_base_url: str
    invitacion_ttl_dias: int
    email_adaptador: AdaptadorDeEmail
    smtp_host: str
    smtp_port: int
    smtp_usuario: str
    smtp_password: str
    smtp_remitente: str
    smtp_tls: bool
    smtp_timeout_segundos: int
    secrets_encryption_key: str
    integracion_timeout_segundos: int
    whatsapp_adaptador: AdaptadorDeWhatsApp
    whatsapp_graph_url: str
    whatsapp_graph_version: str
    whatsapp_timeout_segundos: int
    whatsapp_sondeo_minutos: int
    #: Cada cuántos minutos Beat concilia las plantillas de WhatsApp de cada empresa con Meta
    #: (U6). La revisión tarda hasta 24 h y la consulta cuesta una llamada por empresa.
    whatsapp_plantillas_minutos: int
    #: Cada cuántos minutos Beat despacha el barrido de recordatorios de turno (U8, D-U8-16). 15
    #: divide a 60: el recordatorio llega a lo sumo con un cuarto de hora de atraso respecto de su
    #: momento ideal, y las esperas del reintento (15 y 30 min) caen en múltiplos del intervalo.
    recordatorio_de_turno_minutos: int
    #: El secreto con el que Meta firma el webhook entrante (HS-T2). **Vacío significa que
    #: ninguna firma valida**, igual que el de MercadoPago: lo cómodo —aceptar todo mientras
    #: no haya secreto— convierte un despliegue mal configurado en un endpoint público que le
    #: habla a los clientes de una empresa.
    whatsapp_webhook_secret: str
    #: El token del handshake `GET` con el que Meta verifica la URL al registrarla.
    whatsapp_webhook_verify_token: str
    #: How often Beat retires tasks that ran out of attempts (HS-T6 RN-02).
    dlq_barrido_minutos: int
    #: spreadsheet_sync (HU-E2-04). Cloudflare R2 holds the uploaded workbooks.
    planilla_adaptador: AdaptadorDePlanilla
    almacenamiento_adaptador: AdaptadorDeAlmacenamiento
    #: Sólo para `DISCO`. Vacío usa un directorio bajo el temporal del sistema, para que
    #: arrancar sin configurar nada siga funcionando.
    almacenamiento_directorio: str
    r2_endpoint: str
    r2_bucket: str
    r2_access_key_id: str
    r2_secret_access_key: str
    #: The LLM (ADR-0007). `llm_modelo` is a plain string on purpose: pinning it to a
    #: literal here would mean a release to try a different model.
    llm_adaptador: AdaptadorDeModelo
    anthropic_api_key: str
    llm_modelo: str
    llm_timeout_segundos: float
    llm_max_tokens: int
    #: How often Beat re-reads live spreadsheets and pushes the write-back (HU-E3-04).
    sync_planillas_minutos: int
    #: reference_data + billing: WSFEv1 (ADR-0008). Separate hosts for homologacion and
    #: produccion, like every other ARCA service.
    catalogos_fiscales_adaptador: AdaptadorDeCatalogos
    arca_wsfe_url_homologacion: str
    arca_wsfe_url_produccion: str
    parametros_fiscales_horas: int
    #: How often Beat re-checks documents whose fate ARCA never answered (decision D17).
    #: Five minutes in production; staging raises it so the database can sleep.
    billing_reconciliacion_minutos: int

    @property
    def arca_wsfe_url(self) -> str:
        """The one the environment actually talks to.

        Resolved here rather than at the call site for the reason `ConfiguracionSoap`
        gives: choosing between practising and invoicing for real must never be a default.
        """
        return (
            self.arca_wsfe_url_produccion
            if self.entorno is Entorno.PRODUCTION
            else self.arca_wsfe_url_homologacion
        )

    #: The retry ceiling the sweep judges against. Shares its default with
    #: `PoliticaDeReintentos` in `workers/base.py`; a mismatch would mean tasks are
    #: retired either before or long after they stopped being retried.
    dlq_max_intentos: int
    whatsapp_sondeo_maximo_dias: int
    arca_adaptador: AdaptadorDeArca
    #: ARCA's taxpayer registry, switched apart from WSFE. In `staging` it stays simulated:
    #: the homologación registry does not know the fictitious CUITs every test company uses
    #: (checked 2026-10-08), while invoicing goes to ARCA for a real CAE.
    arca_padron_adaptador: AdaptadorDeArca
    arca_wsaa_url_homologacion: str
    arca_wsaa_url_produccion: str
    arca_padron_url_homologacion: str
    arca_padron_url_produccion: str
    arca_timeout_segundos: int
    arca_margen_renovacion_minutos: int
    #: ADR-0014. The platform certificate and its private key, PEM, one after the other.
    #: Empty only with the simulator: with ARCA real it is how every company is reached.
    arca_credencial_plataforma: bytes
    mercadopago_adaptador: AdaptadorDeMercadoPago
    mercadopago_client_id: str
    mercadopago_client_secret: str
    mercadopago_redirect_uri: str
    mercadopago_auth_url: str
    mercadopago_api_url: str
    mercadopago_timeout_segundos: int
    mercadopago_margen_renovacion_dias: int
    #: HS-T1 RN-01. **Sin secreto configurado, ninguna firma vale**: lo cómodo sería aceptar
    #: todo mientras no haya secreto, y eso convierte un despliegue mal configurado en un
    #: endpoint público que mueve el estado de los cobros.
    mercadopago_webhook_secret: str
    #: A dónde vuelve el cliente después de pagar (HU-E6-03). Es el panel, no la API.
    mercadopago_url_de_retorno: str
    #: HS-T1. La raíz pública de **la API**, a la que MercadoPago avisa cada pago. Vacía sólo
    #: con el simulador: con MercadoPago real, un link sin ella cobra y nunca avisa.
    mercadopago_url_de_notificaciones: str
    mercadopago_autorizacion_ttl_minutos: int

    @property
    def es_produccion(self) -> bool:
        return self.entorno is Entorno.PRODUCTION

    @classmethod
    def desde_entorno(cls) -> Settings:
        entorno = Entorno(_opcional("APP_ENV", Entorno.LOCAL.value))
        redis_url = _requerida("REDIS_URL")
        mercadopago = _adaptador_de_mercadopago(entorno)
        arca = _adaptador_de_arca(entorno)
        arca_padron = _adaptador_del_padron(entorno, arca)
        return cls(
            entorno=entorno,
            database_url=_requerida("DATABASE_URL"),
            # Migrations connect as the table owner; the application does not. That is
            # what makes Row-Level Security real — see migrations/versions/0001.
            database_url_migrations=_requerida("DATABASE_URL_MIGRATIONS"),
            redis_url=redis_url,
            celery_broker_url=_opcional("CELERY_BROKER_URL", redis_url),
            celery_result_backend=_opcional("CELERY_RESULT_BACKEND", redis_url),
            log_level=_opcional("LOG_LEVEL", "INFO"),
            # No default: a JWT secret that falls back to a constant is every
            # deployment signing tokens the world can forge.
            jwt_secret=_requerida("JWT_SECRET"),
            jwt_access_ttl_minutos=_entero("JWT_ACCESS_TTL_MINUTOS", 15),
            refresh_ttl_dias=_entero("REFRESH_TTL_DIAS", 30),
            terminos_version_vigente=_opcional("TERMINOS_VERSION_VIGENTE", "1.0"),
            # Platform-wide OAuth client, not per company. Optional so the API can boot
            # without Google configured; the endpoint refuses instead of the process
            # failing to start.
            google_oauth_client_id=_opcional("GOOGLE_OAUTH_CLIENT_ID", ""),
            google_oauth_client_secret=_opcional("GOOGLE_OAUTH_CLIENT_SECRET", ""),
            google_oauth_redirect_uri=_opcional("GOOGLE_OAUTH_REDIRECT_URI", ""),
            # The invitation email carries a link back into the panel; without this it
            # would carry a broken one, which is a support ticket per invitation.
            app_base_url=_opcional("APP_BASE_URL", "http://localhost:3000"),
            invitacion_ttl_dias=_entero("INVITACION_TTL_DIAS", 7),
            email_adaptador=_adaptador_de_email(entorno),
            smtp_host=_opcional("SMTP_HOST", ""),
            smtp_port=_entero("SMTP_PORT", 587),
            smtp_usuario=_opcional("SMTP_USUARIO", ""),
            smtp_password=_opcional("SMTP_PASSWORD", ""),
            # No default, for the same reason as JWT_SECRET: a fallback key means every
            # deployment encrypts company tax credentials with a constant the repository
            # knows. See contexts/integrations/infrastructure/cifrado.py.
            secrets_encryption_key=_requerida("SECRETS_ENCRYPTION_KEY"),
            integracion_timeout_segundos=_entero("INTEGRACION_TIMEOUT_SEGUNDOS", 5),
            whatsapp_adaptador=_adaptador_de_whatsapp(entorno),
            whatsapp_graph_url=_opcional("WHATSAPP_GRAPH_URL", "https://graph.facebook.com"),
            # Pinned by configuration, never hardcoded: Meta deprecates a Graph version
            # roughly every quarter, and the fix must not require a release.
            whatsapp_graph_version=_opcional("WHATSAPP_GRAPH_VERSION", "v21.0"),
            whatsapp_timeout_segundos=_entero("WHATSAPP_TIMEOUT_SEGUNDOS", 10),
            # 30 minutes against a wait Meta measures in days (HU-E2-03 RN-02): it bounds
            # the delay to about 1% of the wait at 48 calls per number per day.
            whatsapp_sondeo_minutos=_intervalo_en_minutos("WHATSAPP_SONDEO_MINUTOS", 30),
            whatsapp_plantillas_minutos=_intervalo_en_minutos("WHATSAPP_PLANTILLAS_MINUTOS", 30),
            recordatorio_de_turno_minutos=_intervalo_en_minutos(
                "RECORDATORIO_DE_TURNO_MINUTOS", 15
            ),
            whatsapp_webhook_secret=_opcional("WHATSAPP_WEBHOOK_SECRET", ""),
            whatsapp_webhook_verify_token=_opcional("WHATSAPP_WEBHOOK_VERIFY_TOKEN", ""),
            dlq_barrido_minutos=_intervalo_en_minutos("DLQ_BARRIDO_MINUTOS", 15),
            planilla_adaptador=_adaptador_de_planilla(entorno),
            almacenamiento_adaptador=_adaptador_de_almacenamiento(entorno),
            almacenamiento_directorio=_opcional("ALMACENAMIENTO_DIRECTORIO", ""),
            r2_endpoint=_opcional("R2_ENDPOINT", ""),
            r2_bucket=_opcional("R2_BUCKET", ""),
            r2_access_key_id=_opcional("R2_ACCESS_KEY_ID", ""),
            r2_secret_access_key=_opcional("R2_SECRET_ACCESS_KEY", ""),
            llm_adaptador=_adaptador_de_modelo(entorno),
            anthropic_api_key=_opcional("ANTHROPIC_API_KEY", ""),
            llm_modelo=_opcional("LLM_MODELO", MODELO_POR_DEFECTO),
            llm_timeout_segundos=float(_entero("LLM_TIMEOUT_SEGUNDOS", 30)),
            llm_max_tokens=_entero("LLM_MAX_TOKENS", 4096),
            sync_planillas_minutos=_intervalo_en_minutos("SYNC_PLANILLAS_MINUTOS", 60),
            catalogos_fiscales_adaptador=_adaptador_de_catalogos(entorno),
            arca_wsfe_url_homologacion=_opcional(
                "ARCA_WSFE_URL_HOMOLOGACION",
                "https://wswhomo.afip.gov.ar/wsfev1/service.asmx",
            ),
            arca_wsfe_url_produccion=_opcional(
                "ARCA_WSFE_URL_PRODUCCION", "https://servicios1.afip.gov.ar/wsfev1/service.asmx"
            ),
            parametros_fiscales_horas=_intervalo_en_horas("PARAMETROS_FISCALES_HORAS", 24),
            billing_reconciliacion_minutos=_intervalo_en_minutos(
                "BILLING_RECONCILIACION_MINUTOS", 5
            ),
            dlq_max_intentos=_entero("DLQ_MAX_INTENTOS", DLQ_MAX_INTENTOS_POR_DEFECTO),
            # More than double RN-02's 72-hour ceiling. Without it, a number Meta never
            # answers about is polled forever.
            whatsapp_sondeo_maximo_dias=_entero("WHATSAPP_SONDEO_MAXIMO_DIAS", 7),
            arca_adaptador=arca,
            arca_padron_adaptador=arca_padron,
            arca_credencial_plataforma=_credencial_de_plataforma(
                AdaptadorDeArca.ARCA if AdaptadorDeArca.ARCA in (arca, arca_padron) else arca
            ),
            # Two separate hosts, unlike Meta. Which one is used comes from `APP_ENV`, so
            # the environment decides whether a document is a rehearsal or irreversible.
            arca_wsaa_url_homologacion=_opcional(
                "ARCA_WSAA_URL_HOMOLOGACION", "https://wsaahomo.afip.gov.ar/ws/services/LoginCms"
            ),
            arca_wsaa_url_produccion=_opcional(
                "ARCA_WSAA_URL_PRODUCCION", "https://wsaa.afip.gov.ar/ws/services/LoginCms"
            ),
            # The taxpayer registry is a different host from WSAA and splits its
            # environments the same way. Same flag, same consequence if it is wrong.
            arca_padron_url_homologacion=_opcional(
                "ARCA_PADRON_URL_HOMOLOGACION",
                "https://awshomo.afip.gov.ar/sr-padron/webservices/personaServiceA5",
            ),
            arca_padron_url_produccion=_opcional(
                "ARCA_PADRON_URL_PRODUCCION",
                "https://aws.afip.gov.ar/sr-padron/webservices/personaServiceA5",
            ),
            # Longer than Meta's: ARCA is slower, and a login that times out on a busy
            # morning looks to the Administrator exactly like a rejected certificate.
            arca_timeout_segundos=_entero("ARCA_TIMEOUT_SEGUNDOS", 15),
            arca_margen_renovacion_minutos=_entero("ARCA_MARGEN_RENOVACION_MINUTOS", 30),
            # Renewing a certificate at ARCA takes days, so finding out on the day it
            # expired means not being able to invoice.
            mercadopago_adaptador=mercadopago,
            mercadopago_url_de_notificaciones=_url_de_notificaciones(mercadopago),
            # Our application's credentials, not a company's — the same shape as the
            # Google OAuth client. What is per company are the tokens the flow returns,
            # and those live encrypted in the database.
            mercadopago_client_id=_opcional("MERCADOPAGO_CLIENT_ID", ""),
            mercadopago_client_secret=_opcional("MERCADOPAGO_CLIENT_SECRET", ""),
            # Has to match, character for character, the URI registered in MercadoPago and
            # the one repeated when the code is exchanged. Derived from APP_BASE_URL so
            # the two cannot drift apart in a deployment that only sets one of them.
            mercadopago_redirect_uri=_opcional(
                "MERCADOPAGO_REDIRECT_URI",
                f"{_opcional('APP_BASE_URL', 'http://localhost:3000').rstrip('/')}"
                f"/configuracion/integraciones",
            ),
            # One API host for every environment, unlike ARCA: what separates a test
            # account from a real one is `live_mode`, not the address.
            mercadopago_auth_url=_opcional(
                "MERCADOPAGO_AUTH_URL", "https://auth.mercadopago.com.ar"
            ),
            mercadopago_api_url=_opcional("MERCADOPAGO_API_URL", "https://api.mercadopago.com"),
            mercadopago_timeout_segundos=_entero("MERCADOPAGO_TIMEOUT_SEGUNDOS", 10),
            # The access token lasts about 180 days. Fifteen leaves a fortnight of daily
            # retries before anything breaks, which is more than any outage this system
            # can survive anyway.
            mercadopago_margen_renovacion_dias=_entero("MERCADOPAGO_MARGEN_RENOVACION_DIAS", 15),
            mercadopago_webhook_secret=_opcional("MERCADOPAGO_WEBHOOK_SECRET", ""),
            mercadopago_url_de_retorno=_opcional(
                "MERCADOPAGO_URL_DE_RETORNO", "http://localhost:3000/cobros"
            ),
            # Longer than anyone takes to press a button, shorter than a tab left open
            # over lunch — which is the case this window exists to expire.
            mercadopago_autorizacion_ttl_minutos=_entero(
                "MERCADOPAGO_AUTORIZACION_TTL_MINUTOS", 10
            ),
            smtp_remitente=_opcional("SMTP_REMITENTE", "CheatSheet <no-reply@localhost>"),
            smtp_tls=_booleano("SMTP_TLS", True),
            smtp_timeout_segundos=_entero("SMTP_TIMEOUT_SEGUNDOS", 10),
        )

    @property
    def google_oauth_configurado(self) -> bool:
        return bool(self.google_oauth_client_id and self.google_oauth_client_secret)
