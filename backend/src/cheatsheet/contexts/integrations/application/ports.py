"""Ports of the integrations context.

This module and `integraciones.py` are the **published contract** of
[ADR-0003](../../../../../docs/adr/0003-integrations-open-host-service.md): any context
may call what lives in `application/`, and `domain/` and `infrastructure/` stay private.
Nothing here imports from another context — an Open Host Service that depended on its
clients would not be one.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from cheatsheet.contexts.integrations.domain.configuracion import ConfiguracionDeIntegracion
from cheatsheet.contexts.integrations.domain.ticket import ServicioDeArca, TicketDeAcceso
from cheatsheet.contexts.integrations.domain.valores import (
    CredencialCifrada,
    EstadoDeConexion,
    SistemaExterno,
)
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.fiscal import CondicionIVA


class PortRepositorioIntegraciones(Protocol):
    async def agregar(self, configuracion: ConfiguracionDeIntegracion) -> None: ...
    async def guardar(self, configuracion: ConfiguracionDeIntegracion) -> None: ...
    async def buscar(
        self, empresa_id: EmpresaId, sistema: SistemaExterno
    ) -> ConfiguracionDeIntegracion | None: ...
    async def listar(self, empresa_id: EmpresaId) -> list[ConfiguracionDeIntegracion]: ...
    async def listar_pendientes(
        self, empresa_id: EmpresaId
    ) -> list[ConfiguracionDeIntegracion]: ...


class PortRepositorioTickets(Protocol):
    """Where the short-lived sessions derived from a credential live (ADR-0004)."""

    async def agregar(self, ticket: TicketDeAcceso) -> None: ...
    async def guardar(self, ticket: TicketDeAcceso) -> None: ...
    async def buscar(
        self, empresa_id: EmpresaId, servicio: ServicioDeArca
    ) -> TicketDeAcceso | None: ...


class PortCifradoDeCredenciales(Protocol):
    """Encrypts and decrypts a credential at rest.

    The adapter lives in `integrations/infrastructure/` and nowhere else. That placement
    is what makes ADR-0003's "decryption never leaves the context" a fact rather than a
    convention: a cipher in `platform/` would be importable by any module, and the claim
    would rest on nobody happening to do it.
    """

    def cifrar(self, plano: bytes) -> CredencialCifrada: ...
    def descifrar(self, credencial: CredencialCifrada) -> bytes: ...


@dataclass(frozen=True, slots=True)
class ResultadoDeVerificacion:
    """What a live check found. `detalle` is what the Atención badge shows next to it.

    `parametros` carries whatever the provider reported about itself and is **merged**
    into the row, never substituted for it. Today that is HU-E2-03 RN-03 — the verified
    display name and the line quality Meta reports — and the field is generic rather than
    WhatsApp-shaped because a provider-specific DTO in the published contract is what
    point 5 of ADR-0003 forbids.
    """

    estado: EstadoDeConexion
    detalle: str | None = None
    parametros: dict[str, Any] = field(default_factory=dict)


class PortVerificadorDeConexion(Protocol):
    """Asks one external service whether the stored credential still works.

    Implementations own their timeout, their retries with backoff and their failure
    handling (CLAUDE.md §5). The use case owns only the guarantee that a slow one does
    not delay the others.
    """

    async def verificar(
        self, credencial: bytes, parametros: dict[str, Any]
    ) -> ResultadoDeVerificacion: ...


@dataclass(frozen=True, slots=True)
class MaterialDeConexion:
    """What the connect endpoint received, on its way to the provider adapter.

    Opaque bytes plus free parameters, because the three providers disagree about what a
    credential even is: ARCA takes a certificate and a private key, MercadoPago an OAuth
    authorization code, Meta a phone number and a token. Giving each its own DTO here
    would put provider-specific shapes in the published contract, which point 5 of
    ADR-0003 forbids.
    """

    contenido: bytes
    parametros: dict[str, Any]
    #: One-time secrets the provider needs to finish the handshake and that must **not**
    #: outlive it: PKCE's `code_verifier`. A separate bag rather than another key in
    #: `parametros`, because `parametros` is merged onto the aggregate and persisted —
    #: which is right for "which phone number" and wrong for a secret whose whole purpose
    #: is to be used once and forgotten.
    efimeros: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TicketEmitido:
    """A named, expiring secret the provider handed back besides the credential itself.

    Generic on purpose, and it is earned rather than speculative: ARCA returns an access
    ticket per service (ADR-0004) and MercadoPago's OAuth exchange will return a refresh
    token with its own lifetime. Neither shape is provider-specific — a name, some opaque
    bytes and an expiry — so this stays inside what point 5 of ADR-0003 allows in the
    published contract.

    `contenido` is plaintext here and is encrypted by the use case before it is stored.
    It never reaches an aggregate in this form.
    """

    servicio: ServicioDeArca
    contenido: bytes
    expira_en: datetime


@dataclass(frozen=True, slots=True)
class TicketVigente:
    """What a consumer of the Open Host Service receives when it asks for a ticket.

    Never the certificate, never the private key, never the ciphertext — the same rule
    ADR-0003 point 3 sets for credentials, applied to the session derived from one.
    """

    servicio: ServicioDeArca
    contenido: bytes
    expira_en: datetime


class PortEmisorDeTickets(Protocol):
    """Mints a fresh access ticket from a credential.

    Separate from `PortConectorDeIntegracion` because minting happens long after
    connecting: a ticket lasts hours and a credential lasts years, so renewal is its own
    operation with its own failure modes.
    """

    async def emitir(self, credencial: bytes, servicio: ServicioDeArca) -> TicketEmitido: ...


@dataclass(frozen=True, slots=True)
class ResultadoDeConexion:
    """What the provider answered: the credential to store, and where that leaves us.

    **The state is part of the answer, and that is the point** — decision D-a of
    `conexion-whatsapp`. ARCA and MercadoPago validate synchronously and come back
    `CONECTADO`. Meta accepts the credential and then reviews the number for 24 to 72
    hours (HU-E2-03 RN-01), so it comes back `PENDIENTE`. Without this, `ConectarIntegracion`
    would have to ask "is this WhatsApp?" — the per-provider conditional the adapter
    registry exists precisely to avoid.

    `credencial` is what gets encrypted and persisted; it is not necessarily what arrived.
    An OAuth exchange returns a different token from the code it was given.
    """

    credencial: bytes
    estado: EstadoDeConexion = EstadoDeConexion.CONECTADO
    detalle: str | None = None
    parametros: dict[str, Any] = field(default_factory=dict)
    #: Anything the provider minted while proving the credential works, which has to be
    #: kept. ARCA's WSAA hands back an access ticket during validation and **refuses to
    #: issue another while it is alive**, so discarding it would lock the company out for
    #: up to twelve hours. The use case encrypts and stores these; the adapter does not
    #: touch a repository.
    tickets: tuple[TicketEmitido, ...] = ()


class PortConectorDeIntegracion(Protocol):
    """Validates connection material against the provider before anything is stored.

    HU-E2-01 RN-02 and HU-E2-02 RN-02 both require validation *before* the integration is
    marked active, so this returns the credential to persist and raises when the provider
    says no.
    """

    async def conectar(self, material: MaterialDeConexion) -> ResultadoDeConexion: ...


@dataclass(frozen=True, slots=True)
class AvisoDeIntegracion:
    """One notice about an integration whose state changed on its own.

    **`destinatarios` arrives resolved, and that is deliberate — decision D-c.** Who the
    administrators of a company are is `identity` data, and ADR-0003 lists `identity`
    among this context's consumers: reaching back into it would make the Open Host Service
    depend on a client of its own. So the composition root — the Celery task — reads the
    recipients and passes them in. What stays here is *when* to notify; what stays outside
    is *whom*.
    """

    destinatarios: tuple[str, ...]
    sistema: SistemaExterno
    estado: EstadoDeConexion
    detalle: str | None


class PortAvisoDeIntegracion(Protocol):
    """Tells the Administrator that a provider answered while nobody was looking.

    Only the asynchronous outcomes go through here (HU-E2-03: the verification completed,
    or it failed). The synchronous ones need no push — whoever pressed the button is
    looking at the screen that already shows the answer.
    """

    async def avisar(self, aviso: AvisoDeIntegracion) -> None: ...


@dataclass(frozen=True, slots=True)
class DatosDePadron:
    """What ARCA's registry knows about one tax id.

    Part of the published contract, and shaped for the question `identity` asks rather
    than for what ARCA answers: the provider's vocabulary stops at the adapter. Every
    field except `cuit` may be absent, because the registry itself is uneven — a company
    without a declared VAT status is unusual, not impossible, and inventing one here would
    decide which kind of `Comprobante` epic 5 may issue.

    `CondicionIVA` travels because it lives in the Shared Kernel (`shared/fiscal.py`). It
    is not `identity`'s type crossing a boundary: it is vocabulary both contexts own.
    """

    cuit: str
    razon_social: str | None
    condicion_iva: CondicionIVA | None
    #: `False` when the tax id exists but is deregistered. It does **not** mean "not
    #: found": that is a `None` result, and the two lead to opposite decisions.
    activo: bool


class PortConsultaDePadron(Protocol):
    """Looks a tax id up in ARCA's registry with an access ticket already in hand.

    `parametros` is the integration's own stored parameters, not the caller's: ARCA
    demands to know *whose* certificate is asking, and that CUIT was extracted from the
    certificate when the company connected. Passing the whole bag keeps the parameter
    keys — which are ARCA's — inside ARCA's adapter.

    Returns `None` when the registry does not know the tax id. **Never** returns `None`
    for an outage; that raises, and the difference is what stops a bad afternoon at ARCA
    from turning into a rejected CUIT.
    """

    async def consultar(
        self, *, ticket: bytes, parametros: Mapping[str, Any], cuit: str
    ) -> DatosDePadron | None: ...


@dataclass(frozen=True, slots=True)
class PedidoDeAutorizacion:
    """What the authorization URL of an OAuth2 flow has to carry.

    `estado` is the CSRF token the provider echoes back; `desafio` is the PKCE
    `code_challenge`. **The verifier that produced the challenge is not here**, and that
    is the point of PKCE: it stays on our side until the code is exchanged, so a stolen
    authorization code is useless to whoever stole it.
    """

    estado: str
    desafio: str


class PortAutorizacionOAuth(Protocol):
    """Builds the URL the Administrator's browser is sent to.

    Opens no socket: the whole operation is assembling a query string. It is a port
    anyway because the client id and the provider's host are configuration, and a use
    case that read them would be reaching into `platform/`.
    """

    def url_de_autorizacion(self, pedido: PedidoDeAutorizacion) -> str: ...


@dataclass(frozen=True, slots=True)
class AutorizacionPendiente:
    """What has to survive while the Administrator is away at the provider's site.

    The company is stored rather than re-read from the session on the way back, and the
    two are then compared: whoever returns must be the company that left. Without that,
    a `state` issued for one company completes a connection for another.
    """

    empresa_id: EmpresaId
    sistema: SistemaExterno
    verificador: str


class PortMemoriaDeAutorizacion(Protocol):
    """Where an authorization in flight lives between the two halves of the flow.

    Short-lived by nature — ten minutes, not a row in a table — so the adapter is Redis
    and the entries expire on their own. Nothing here is a credential: a `state` that
    outlives its window is worth nothing to anybody.
    """

    async def guardar(
        self, estado: str, pendiente: AutorizacionPendiente, ttl_segundos: int
    ) -> None: ...

    async def consumir(self, estado: str) -> AutorizacionPendiente | None:
        """Read **and delete** in one operation, returning `None` if it was not there.

        One operation and not a read followed by a delete: two callbacks arriving at the
        same instant with the same `state` must not both find it. That is what makes a
        `state` single-use under concurrency rather than only in a single-threaded test.
        """
        ...


class PortRenovacionDeCredencial(Protocol):
    """Trades a credential that is about to expire for a fresh one.

    Separate from `PortConectorDeIntegracion` because the two differ in what they need
    and in what a failure means. Connecting starts from something a person just supplied
    and a rejection is shown on the screen they are looking at; renewing starts from what
    is already stored and a rejection means the integration has to be marked inactive and
    the Administrator told (HU-E2-02 RN-03), with nobody watching.

    Returns the same `ResultadoDeConexion` as connecting, because the outcome is the same
    kind of thing: a credential to store and the state it leaves us in.
    """

    async def renovar(self, credencial: bytes) -> ResultadoDeConexion: ...


class PortRegistroDeAdaptadores(Protocol):
    """Resolves the adapters of one system.

    The single seam each unit of the epic touches: `conexion-arca` registered the real
    ARCA trio, `padron-y-datos-fiscales` added its fourth adapter, and
    `conexion-mercadopago` — the last one — registers the two OAuth2 needs.

    **No system implements all six, and none is expected to.** ARCA mints access tickets
    and has a taxpayer registry; MercadoPago authorizes and renews; WhatsApp does neither.
    Optional slots on one registry rather than a registry per capability, because they are
    all resolved by the same key and replaced by the same unit.
    """

    def conector(self, sistema: SistemaExterno) -> PortConectorDeIntegracion | None: ...
    def verificador(self, sistema: SistemaExterno) -> PortVerificadorDeConexion | None: ...
    def emisor_de_tickets(self, sistema: SistemaExterno) -> PortEmisorDeTickets | None: ...
    def consulta_de_padron(self, sistema: SistemaExterno) -> PortConsultaDePadron | None: ...
    def autorizacion(self, sistema: SistemaExterno) -> PortAutorizacionOAuth | None: ...
    def renovador(self, sistema: SistemaExterno) -> PortRenovacionDeCredencial | None: ...
