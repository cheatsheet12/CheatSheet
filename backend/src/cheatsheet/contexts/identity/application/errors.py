"""Application-level conditions of the identity context."""

from __future__ import annotations

from cheatsheet.shared.errors import (
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
