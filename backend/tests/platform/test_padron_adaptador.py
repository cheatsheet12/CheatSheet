"""`ARCA_PADRON_ADAPTADOR`: el padrón se elige aparte de WSFE.

En staging queda simulado porque el padrón de homologación no conoce las CUIT ficticias de
las empresas de prueba (consulta real del 08/10/2026), mientras la facturación va a ARCA.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from cheatsheet.contexts.integrations.domain.valores import SistemaExterno
from cheatsheet.contexts.integrations.infrastructure.arca.adaptadores import EmisorArcaDeTickets
from cheatsheet.contexts.integrations.infrastructure.arca.padron import ClientePadronA5
from cheatsheet.contexts.integrations.infrastructure.arca.simulado import (
    ArcaSimuladoPorDelegacion,
)
from cheatsheet.contexts.integrations.infrastructure.registro import (
    RegistroDeAdaptadores,
    emisor_de_arca,
)
from cheatsheet.platform.settings import (
    AdaptadorDeArca,
    ConfiguracionFaltante,
    Entorno,
    _adaptador_del_padron,
)
from cheatsheet.shared.clock import RelojDelSistema

from tests.conftest import settings_de_prueba


@pytest.fixture(autouse=True)
def _sin_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARCA_PADRON_ADAPTADOR", raising=False)


def test_por_defecto_sigue_a_arca() -> None:
    assert _adaptador_del_padron(Entorno.STAGING, AdaptadorDeArca.ARCA) is AdaptadorDeArca.ARCA


def test_en_staging_se_puede_simular_aparte(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCA_PADRON_ADAPTADOR", "simulado")

    elegido = _adaptador_del_padron(Entorno.STAGING, AdaptadorDeArca.ARCA)

    assert elegido is AdaptadorDeArca.SIMULADO


def test_en_produccion_el_padron_simulado_no_arranca(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCA_PADRON_ADAPTADOR", "simulado")

    with pytest.raises(ConfiguracionFaltante, match="produccion"):
        _adaptador_del_padron(Entorno.PRODUCTION, AdaptadorDeArca.ARCA)


def test_un_valor_desconocido_se_rechaza(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCA_PADRON_ADAPTADOR", "a-medias")

    with pytest.raises(ConfiguracionFaltante, match="ARCA_PADRON_ADAPTADOR"):
        _adaptador_del_padron(Entorno.STAGING, AdaptadorDeArca.ARCA)


def test_arca_real_con_padron_simulado_arma_el_simulador_solo_para_el_padron() -> None:
    settings = replace(
        settings_de_prueba(),
        entorno=Entorno.STAGING,
        arca_adaptador=AdaptadorDeArca.ARCA,
        arca_padron_adaptador=AdaptadorDeArca.SIMULADO,
    )

    registro = RegistroDeAdaptadores.desde_settings(settings)

    assert isinstance(registro.consulta_de_padron(SistemaExterno.ARCA), ArcaSimuladoPorDelegacion)
    assert not isinstance(registro.conector(SistemaExterno.ARCA), ArcaSimuladoPorDelegacion)


def test_padron_real_usa_wsaa_aunque_arca_este_simulada() -> None:
    settings = replace(
        settings_de_prueba(),
        entorno=Entorno.STAGING,
        arca_adaptador=AdaptadorDeArca.SIMULADO,
        arca_padron_adaptador=AdaptadorDeArca.ARCA,
    )

    registro = RegistroDeAdaptadores.desde_settings(settings)

    assert isinstance(registro.consulta_de_padron(SistemaExterno.ARCA), ClientePadronA5)
    assert isinstance(emisor_de_arca(settings, RelojDelSistema()), EmisorArcaDeTickets)
