"""RN-01 de HU-E4-05 también limpia la condición de IVA de la planilla antes de mapearla.

Vive en su propio archivo para que `tipos-de-comprobante-por-receptor`, que agrega
`IVA_NO_ALCANZADO` a la misma traducción, pueda integrarse en cualquier orden.
"""

from __future__ import annotations

import pytest
from cheatsheet.contexts.master_data.application.ingesta import _condicion_iva
from cheatsheet.shared.fiscal import CondicionIVA


@pytest.mark.parametrize(
    "crudo", ["  responsable   inscripto ", "Responsable\xa0Inscripto", "RESPONSABLE\tINSCRIPTO"]
)
def test_la_condicion_de_iva_se_limpia_antes_de_mapearse(crudo: str) -> None:
    assert _condicion_iva(crudo) is CondicionIVA.RESPONSABLE_INSCRIPTO


def test_una_condicion_desconocida_sigue_quedando_vacia() -> None:
    assert _condicion_iva("no se") is None
    assert _condicion_iva("   ") is None
