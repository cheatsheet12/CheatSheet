"""Application-level conditions of the integrations context."""

from __future__ import annotations

from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada, OperacionNoPermitida


class PermisoDenegado(OperacionNoPermitida):
    """The role does not allow this. Answered as 403.

    HU-E2-05 gives an Operador read and verify; everything that writes a credential is
    the Administrator's.
    """


class SistemaNoConfigurable(EntradaInvalida):
    """The system has no connector registered in this epic.

    An `EntradaInvalida` — answered as 422 — and not the default 409: `GOOGLE_SHEETS` is a
    well-formed member of the enum, so the shape was right and the meaning was not, which
    is exactly what that error is for.

    `GOOGLE_SHEETS` and `EXCEL_ONLINE` are in the DER enum and on the screen, but their
    connection is HU-E2-04, which belongs to epic 4. Asking to connect one answers with
    this rather than with a 500 from an empty registry lookup.
    """


class ConexionRechazada(EntradaInvalida):
    """The provider refused the credentials (HU-E2-01 RN-02, HU-E2-02 RN-02).

    A domain error, not a failure: the external system worked correctly and said no. The
    integration stays not connected and the screen shows the reason.

    `EntradaInvalida` so it answers 422, because HU-E2-01's acceptance criterion words it
    as "el sistema indica el error de validación" — and because a rejected credential and
    a malformed one are the same thing to whoever is filling in the form.
    """


class ProveedorNoDisponible(RuntimeError):
    """The provider timed out or could not be reached.

    **Not an `ErrorDeDominio`**, for the same reason as `EnvioDeEmailFallido` in identity:
    no business rule was broken, an external system failed. `VerificarConexiones` catches
    this per provider and turns it into `NO_CONECTADO` with a detail, so one unreachable
    service does not take the other three down with it.
    """


class TicketTodaviaVigente(ProveedorNoDisponible):
    """ARCA still holds a live ticket for this certificate and service, and refused another.

    In the application layer so a use case can react to it without importing ARCA's
    adapter: the reaction is "use the one already stored", and when none is stored, wait
    for the live one to expire.
    """


class TicketNoDisponible(OperacionNoPermitida):
    """No usable ARCA access ticket could be produced for this company.

    Raised by `ObtenerTicketDeAcceso`, and therefore seen by **other contexts** —
    `billing` in epic 5, `identity` in the padrón unit. It is deliberately one error and
    not three, because every cause leads the caller to the same place: the company cannot
    operate against ARCA right now, and the reason belongs in the message rather than in
    the type.

    An `OperacionNoPermitida` — answered as 403 — and not an `EntradaInvalida`: nothing
    the caller sent was wrong. The company simply has not connected ARCA, or its
    credential stopped working.
    """


class ConsultaDePadronNoDisponible(ProveedorNoDisponible):
    """The taxpayer registry could not be asked. **Not** "the tax id does not exist".

    Every cause lands here — the company has not connected ARCA, no access ticket could
    be minted, the service timed out, the stored certificate does not declare a CUIT —
    because the caller's reaction is the same in all of them: carry on without the
    registry's opinion, and say so.

    A subclass of `ProveedorNoDisponible` and not of `ConexionRechazada`, and the
    distinction is the point of the unit: an unreachable ARCA must never look like a CUIT
    ARCA rejected. One of those blocks the Administrator; the other must not.
    """


class AutorizacionInvalida(EntradaInvalida):
    """The OAuth round trip came back with something that cannot be trusted.

    One error for four causes — the `state` was never issued, it expired, it was already
    used, or it belongs to another company — and that is deliberate: telling them apart
    on screen would tell whoever is probing which of the four it was.

    An `EntradaInvalida` (422) because the honest reading of the frequent case is stale
    input: a browser tab left open past the ten-minute window. What the Administrator has
    to do is the same in all four cases, and the message says it — start the connection
    again.

    **The dangerous case is the fourth**, and it is why this check lives in the
    application layer instead of at the HTTP edge: without it, anyone who gets an
    Administrator to open a crafted link attaches *their* MercadoPago account to somebody
    else's company, and every payment link of epic 6 collects into the wrong account.
    """


class CuentaDeWhatsAppEnUso(InvarianteViolada):
    """The WhatsApp business account is already linked to another empresa.

    An `InvarianteViolada` — answered as 409 — because the input is well-formed and the
    conflict is with state that exists: the unique index of migration 0036 allows one
    empresa per WABA. Without it, a second empresa registering somebody else's WABA would
    steal or block that company's template webhooks, which resolve the company from the WABA.

    The message never names the other empresa: that would leak who uses the platform.
    """
