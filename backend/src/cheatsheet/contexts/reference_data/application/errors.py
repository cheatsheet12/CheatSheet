"""Errors of `reference_data`.

One, and it is a transport failure with a business meaning: ARCA could not be asked for the
catalogue. HS-T4 RN-04 turns it into «keep the last one and log it» rather than into a
failed operation, so nothing above catches it expecting to abort.
"""

from __future__ import annotations

from cheatsheet.shared.errors import ErrorDeDominio


class CatalogoNoDisponible(ErrorDeDominio):
    """ARCA did not answer, or the company has no ticket to ask with."""
