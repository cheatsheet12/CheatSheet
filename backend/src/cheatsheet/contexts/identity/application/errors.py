"""Application-level conditions of the identity context."""

from __future__ import annotations

from cheatsheet.shared.errors import ErrorDeDominio


class EmailYaRegistrado(ErrorDeDominio):
    """HU-E1-01 RN-03. The story asks the UI to offer signing in instead."""


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
