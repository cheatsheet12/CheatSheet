"""La capa anticorrupción entre `master_data` e `integrations`.

Doce líneas de adaptador, y lo que se prueba de ellas es lo único que puede salir mal:
que la excepción de `integrations` no se filtre hacia arriba, y que `None` siga
significando «ARCA no conoce ese CUIT» y no «ARCA no contestó».
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from cheatsheet.contexts.integrations.application.errors import ConsultaDePadronNoDisponible
from cheatsheet.contexts.integrations.application.ports import DatosDePadron
from cheatsheet.contexts.master_data.application.ports import PadronNoDisponible
from cheatsheet.contexts.master_data.infrastructure.padron import PadronViaIntegraciones
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.fiscal import CondicionIVA

from tests.contexts.master_data.conftest import CUIT_VALIDO

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())


class ConsultaFalsa:
    """Se hace pasar por `ConsultarPadron` de `integrations`, que es lo que el ACL envuelve."""

    def __init__(self, *, datos: DatosDePadron | None, excepcion: Exception | None = None) -> None:
        self.datos = datos
        self.excepcion = excepcion

    async def ejecutar(self, *, empresa_id: EmpresaId, cuit: str) -> DatosDePadron | None:
        del empresa_id, cuit
        if self.excepcion is not None:
            raise self.excepcion
        return self.datos


def _acl(consulta: ConsultaFalsa) -> PadronViaIntegraciones:
    return PadronViaIntegraciones(consulta)  # type: ignore[arg-type]  # doble del caso de uso


async def test_traduce_los_datos_al_vocabulario_de_master_data() -> None:
    datos = DatosDePadron(
        cuit=CUIT_VALIDO,
        razon_social="PANADERIA DONA ROSA SRL",
        condicion_iva=CondicionIVA.RESPONSABLE_INSCRIPTO,
        activo=True,
    )

    resultado = await _acl(ConsultaFalsa(datos=datos)).consultar(
        empresa_id=EMPRESA, cuit=CUIT_VALIDO
    )

    assert resultado is not None
    assert resultado.razon_social == "PANADERIA DONA ROSA SRL"
    assert resultado.condicion_iva is CondicionIVA.RESPONSABLE_INSCRIPTO
    assert resultado.activo is True


async def test_none_sigue_siendo_none() -> None:
    """«ARCA no conoce ese CUIT» cruza la frontera sin convertirse en un error."""
    resultado = await _acl(ConsultaFalsa(datos=None)).consultar(
        empresa_id=EMPRESA, cuit=CUIT_VALIDO
    )

    assert resultado is None


async def test_la_excepcion_de_integrations_no_se_filtra() -> None:
    """Si viajara, cada `except` de `master_data` sería un import de otro contexto."""
    consulta = ConsultaFalsa(
        datos=None, excepcion=ConsultaDePadronNoDisponible("ARCA no esta conectada")
    )

    with pytest.raises(PadronNoDisponible, match="ARCA no esta conectada"):
        await _acl(consulta).consultar(empresa_id=EMPRESA, cuit=CUIT_VALIDO)
