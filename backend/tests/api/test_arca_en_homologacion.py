"""ARCA real contra homologación: lo que homologación no tiene (10/10/2026).

Probado con el certificado de plataforma: ARCA dio CAE a la empresa ficticia en el punto de
venta 1, pero `FEParamGetPtosVenta` respondió `602 Sin Resultados` — homologación no lleva
registro de puntos de venta. Y con el padrón simulado, la consulta igual pedía un ticket real
a WSAA.
"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from cheatsheet.api import arca
from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.contexts.billing.infrastructure.habilitacion import (
    HabilitacionEnArca,
    HabilitacionSimulada,
)
from cheatsheet.contexts.integrations.infrastructure.arca.simulado import TicketDePadronSimulado
from cheatsheet.contexts.integrations.infrastructure.ensamblado import Integraciones
from cheatsheet.platform.settings import (
    AdaptadorDeArca,
    AdaptadorDeCatalogos,
    Entorno,
    Settings,
)
from cheatsheet.platform.wsfe import PortCredencialesDeWsfe
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import settings_de_prueba

#: Nada de esto llega a abrir una transacción: solo se arman piezas.
_SESION = cast(AsyncSession, object())
_UNIDAD = cast(UnidadDeTrabajo, object())


def _wsfe_real(entorno: Entorno) -> Settings:
    return replace(
        settings_de_prueba(entorno), catalogos_fiscales_adaptador=AdaptadorDeCatalogos.WSFE
    )


def test_en_homologacion_los_puntos_de_venta_no_se_le_preguntan_a_arca() -> None:
    habilitacion = arca.armar_habilitacion(_UNIDAD, _wsfe_real(Entorno.STAGING))

    assert isinstance(habilitacion, HabilitacionSimulada)


def test_en_produccion_los_puntos_de_venta_son_los_de_arca(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        arca, "armar_credenciales", lambda *_: cast(PortCredencialesDeWsfe, object())
    )

    habilitacion = arca.armar_habilitacion(_UNIDAD, _wsfe_real(Entorno.PRODUCTION))

    assert isinstance(habilitacion, HabilitacionEnArca)


def test_con_el_padron_simulado_su_ticket_no_sale_de_wsaa() -> None:
    piezas = Integraciones.armar(_SESION, settings_de_prueba(Entorno.STAGING))

    assert isinstance(piezas.tickets_de_padron, TicketDePadronSimulado)


def test_con_el_padron_real_su_ticket_es_el_de_la_plataforma() -> None:
    settings = replace(
        settings_de_prueba(Entorno.STAGING), arca_padron_adaptador=AdaptadorDeArca.ARCA
    )

    piezas = Integraciones.armar(_SESION, settings)

    assert piezas.tickets_de_padron is piezas.tickets_de_plataforma
