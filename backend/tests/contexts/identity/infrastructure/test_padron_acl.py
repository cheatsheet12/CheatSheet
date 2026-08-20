"""El Anti-Corruption Layer entre `identity` e `integrations`.

Doce líneas de código y el único lugar de este contexto que importa otro. Lo que se
prueba es justamente lo que justifica que exista: que el vocabulario del proveedor —su
DTO y su excepción— **no** cruce la frontera. Si `ConsultaDePadronNoDisponible` viajara
hacia arriba, cada `except` de `identity` sería un import de otro contexto.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from cheatsheet.contexts.identity.application.ports import PadronNoDisponible
from cheatsheet.contexts.identity.infrastructure.padron import PadronViaIntegraciones
from cheatsheet.contexts.integrations.application.errors import ConsultaDePadronNoDisponible
from cheatsheet.contexts.integrations.application.ports import DatosDePadron
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.fiscal import CondicionIVA

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())
CUIT = "30712345671"


class ConsultaProgramada:
    """Se hace pasar por `ConsultarPadron` sin arrastrar sus cinco dependencias."""

    def __init__(
        self, *, datos: DatosDePadron | None = None, excepcion: Exception | None = None
    ) -> None:
        self.datos = datos
        self.excepcion = excepcion

    async def ejecutar(self, *, empresa_id: EmpresaId, cuit: str) -> DatosDePadron | None:
        del empresa_id, cuit
        if self.excepcion is not None:
            raise self.excepcion
        return self.datos


def _acl(consulta: ConsultaProgramada) -> PadronViaIntegraciones:
    # El doble satisface la forma que el ACL usa; mypy no lo sabe y no hace falta que lo
    # sepa para este test, que es sobre la traducción y no sobre el cableado.
    return PadronViaIntegraciones(consulta)  # type: ignore[arg-type]


async def test_traduce_los_datos_al_vocabulario_de_identity() -> None:
    datos = DatosDePadron(
        cuit=CUIT,
        razon_social="PANADERIA DONA ROSA SRL",
        condicion_iva=CondicionIVA.RESPONSABLE_INSCRIPTO,
        activo=True,
    )

    traducido = await _acl(ConsultaProgramada(datos=datos)).consultar(empresa_id=EMPRESA, cuit=CUIT)

    assert traducido is not None
    assert traducido.razon_social == "PANADERIA DONA ROSA SRL"
    assert traducido.condicion_iva is CondicionIVA.RESPONSABLE_INSCRIPTO
    assert traducido.activo
    # El `cuit` de ida no vuelve: `identity` ya sabe cuál preguntó.
    assert not hasattr(traducido, "cuit")


async def test_no_encontrado_sigue_siendo_none_y_no_una_excepcion() -> None:
    """La distinción que sostiene la unidad, en el punto donde podría perderse."""
    assert (
        await _acl(ConsultaProgramada(datos=None)).consultar(empresa_id=EMPRESA, cuit=CUIT) is None
    )


async def test_la_excepcion_del_otro_contexto_no_cruza_la_frontera() -> None:
    consulta = ConsultaProgramada(excepcion=ConsultaDePadronNoDisponible("ARCA no responde"))

    with pytest.raises(PadronNoDisponible, match="ARCA no responde"):
        await _acl(consulta).consultar(empresa_id=EMPRESA, cuit=CUIT)
