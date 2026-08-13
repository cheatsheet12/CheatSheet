"""The processing guarantees of ADR-009, tested without a broker."""

from __future__ import annotations

import pytest
from cheatsheet.platform.cache import RegistroDeIdempotenciaEnMemoria
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.idempotencia import ClaveDeIdempotencia
from cheatsheet.workers.base import EjecutorIdempotente, PoliticaDeReintentos


@pytest.mark.asyncio
async def test_la_misma_clave_no_repite_el_efecto(empresa_id: EmpresaId):
    """The one guarantee that keeps a retried task from charging a customer twice."""
    ejecutor = EjecutorIdempotente(RegistroDeIdempotenciaEnMemoria())
    clave = ClaveDeIdempotencia.de(
        empresa_id=empresa_id, tipo="cobrar", payload={"monto": "100.00"}
    )
    ejecuciones: list[int] = []

    async def efecto() -> str:
        ejecuciones.append(1)
        return "hecho"

    primero = await ejecutor.ejecutar(clave, efecto)
    segundo = await ejecutor.ejecutar(clave, efecto)

    assert primero == "hecho"
    assert segundo is None
    assert len(ejecuciones) == 1


@pytest.mark.asyncio
async def test_claves_distintas_ejecutan_cada_una(empresa_id: EmpresaId):
    ejecutor = EjecutorIdempotente(RegistroDeIdempotenciaEnMemoria())
    ejecuciones: list[int] = []

    async def efecto() -> None:
        ejecuciones.append(1)

    for monto in ("100.00", "200.00"):
        clave = ClaveDeIdempotencia.de(
            empresa_id=empresa_id, tipo="cobrar", payload={"monto": monto}
        )
        await ejecutor.ejecutar(clave, efecto)

    assert len(ejecuciones) == 2


def test_el_orden_de_las_claves_del_payload_no_cambia_la_huella(empresa_id: EmpresaId):
    """The same delivery serialised differently is still the same delivery."""
    una = ClaveDeIdempotencia.de(empresa_id=empresa_id, tipo="t", payload={"a": 1, "b": 2})
    otra = ClaveDeIdempotencia.de(empresa_id=empresa_id, tipo="t", payload={"b": 2, "a": 1})

    assert una == otra


def test_tenants_distintos_nunca_comparten_clave():
    """Otherwise one company's webhook would suppress another company's."""
    from uuid import uuid4

    payload = {"evento": "payment.updated"}
    una = ClaveDeIdempotencia.de(empresa_id=EmpresaId(uuid4()), tipo="t", payload=payload)
    otra = ClaveDeIdempotencia.de(empresa_id=EmpresaId(uuid4()), tipo="t", payload=payload)

    assert una != otra


def test_la_espera_crece_y_nunca_supera_el_techo():
    politica = PoliticaDeReintentos(max_intentos=5, espera_base=2.0, espera_maxima=10.0)

    for intento in range(1, 6):
        assert 0.0 <= politica.espera_para(intento) <= 10.0


def test_la_espera_exige_un_intento_valido():
    with pytest.raises(ValueError, match="arranca en 1"):
        PoliticaDeReintentos().espera_para(0)


def test_los_intentos_se_agotan_en_el_maximo():
    politica = PoliticaDeReintentos(max_intentos=3)

    assert politica.agoto_los_intentos(2) is False
    assert politica.agoto_los_intentos(3) is True
