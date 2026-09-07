"""Errors of `spreadsheet_sync`.

Each one exists because a story names a message the user reads. They derive from
`EntradaInvalida` rather than `InvarianteViolada` on purpose: `api/main.py` maps the
former to 422 **and forwards its text**, and the latter to a generic 409 whose detail the
BFF discards. Epic 3 learned that the hard way -- `ClienteDuplicado` is an
`InvarianteViolada`, so its message never reaches the screen and the acceptance criterion
that depends on it is unmet end to end (recorded in `TODO.md` §10).

That is not a workaround. These really are invalid input: a `.pdf` in the drop zone, a
file over the limit, an authorisation the user declined. The 422 is the honest status.
"""

from __future__ import annotations

from cheatsheet.shared.errors import EntradaInvalida


class FormatoDePlanillaNoSoportado(EntradaInvalida):
    """HU-E3-03: something that is not `.xlsx`, `.xls` or `.csv`."""


class ArchivoDemasiadoGrande(EntradaInvalida):
    """HU-E3-03: over 25 MB."""


class PermisosDePlanillaInsuficientes(EntradaInvalida):
    """HU-E2-04: the user did not grant read access, so no link is created."""


class VinculoInexistente(EntradaInvalida):
    """The link is not this company's, or never existed. RLS makes those the same thing."""


class ProveedorDePlanillaNoDisponible(EntradaInvalida):
    """Google or Microsoft did not answer. Distinct from a refusal, and it is not the
    user's fault -- the screen has to say so differently."""
