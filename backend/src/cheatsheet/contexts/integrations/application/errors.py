"""Application-level conditions of the integrations context."""

from __future__ import annotations

from cheatsheet.shared.errors import EntradaInvalida, OperacionNoPermitida


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
