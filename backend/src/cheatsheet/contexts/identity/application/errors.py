"""Application-level conditions of the identity context."""

from __future__ import annotations

from cheatsheet.shared.errors import (
    EntradaInvalida,
    ErrorDeDominio,
    InvarianteViolada,
    OperacionNoPermitida,
)


class EmailYaRegistrado(ErrorDeDominio):
    """HU-E1-01 RN-03, HU-E1-04 RN-03. The story asks the UI to offer signing in instead."""


class PermisoDenegado(OperacionNoPermitida):
    """The role does not allow this (HU-E1-05 RN-03). Answered as 403."""


class UltimoAdministradorActivo(InvarianteViolada):
    """HU-E1-05 RN-02 and HU-E1-06 RN-03: a company always keeps one active Administrator.

    Both stories phrase it as a rule about the *company*, not about the user being
    changed, which is why it is raised by the use case and not by the aggregate.
    """


class InvitacionInvalida(ErrorDeDominio):
    """Unknown, expired, already used or revoked.

    **One error for all four cases, deliberately** — the same reason as
    `CredencialesInvalidas`. Whoever presents a token that is not theirs learns only that
    it does not work, not which of the four ways it failed.
    """


class CuitYaRegistrado(ErrorDeDominio):
    """`empresa.cuit` is unique in the DER: one company, one tax id."""


class CuitInexistenteEnPadron(EntradaInvalida):
    """ARCA's registry does not know this tax id (HU-E1-02 RN-01).

    An `EntradaInvalida` — answered as 422 — for the same reason `ConexionRechazada` is
    one in `integrations`: the acceptance criterion words it as «el sistema indica que el
    CUIT no fue encontrado en ARCA», which is a message beside a field, not a conflict
    with the state of the server.

    Raised **only when the registry actually answered**. A CUIT that could not be checked
    — because ARCA is unreachable, or because the company has not loaded its certificate
    yet — is not this error and must never become it: the whole point of the padrón unit
    is that an outage at ARCA does not read to the Administrator like a rejected CUIT.
    """


class CredencialesInvalidas(ErrorDeDominio):
    """Wrong email, wrong password, or a Google-only account trying a password.

    **One error for all three cases, deliberately.** Distinguishing them tells an
    attacker which emails exist, which turns a login form into an account enumerator.
    """


class SesionInvalida(ErrorDeDominio):
    """The refresh token is unknown, expired, already used or revoked."""


class ReusoDeRefreshDetectado(SesionInvalida):
    """A used token came back. Treated as theft: the whole family is revoked."""


class OAuthFallido(ErrorDeDominio):
    """Google did not return a usable profile."""


class EnvioDeEmailFallido(RuntimeError):
    """The mail server refused or timed out.

    **Not an `ErrorDeDominio`**: no business rule was broken, an external system failed.
    The distinction matters because it decides the answer — a domain error is the user's
    problem to fix, this one is ours to retry.
    """
