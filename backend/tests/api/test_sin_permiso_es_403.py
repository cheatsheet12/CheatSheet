"""Un rol sin permiso se rechaza con 403, en todos los módulos.

PRU-07 lo encontró en staging el 11/10/2026: Solo Lectura no podía emitir un comprobante, pero
la API lo informaba como 422 (`EntradaInvalida`, «datos inválidos») en lugar de 403
(`OperacionNoPermitida`). identity, integrations y master_data ya respondían 403; estos
guardias, no. La seguridad se cumplía; el contrato, no: un cliente no puede distinguir «me
equivoqué en el pedido» de «no tengo permiso».
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from cheatsheet.api.errors import CODIGOS
from cheatsheet.contexts.billing.application import emision, puntos_de_venta
from cheatsheet.contexts.business_config.application import plantillas, reglas
from cheatsheet.contexts.conversational.application import atencion, faqs
from cheatsheet.contexts.observability.application.errors import AccesoALaBitacoraDenegado
from cheatsheet.contexts.payments.application import cobros, reembolsos_comunes
from cheatsheet.contexts.reporting.application import generacion, paquete
from cheatsheet.contexts.scheduling.application import recursos, turnos
from cheatsheet.contexts.spreadsheet_sync.application import vinculos
from cheatsheet.shared.errors import OperacionNoPermitida
from cheatsheet.shared.roles import RolUsuario
from fastapi import status

GUARDIAS_DE_GESTOR: list[Callable[[RolUsuario], None]] = [
    emision._exigir_emisor,
    cobros.exigir_gestor,
    turnos._exigir_gestor,
    generacion._exigir_gestor,
    atencion._exigir_gestor,
]

GUARDIAS_DE_ADMINISTRADOR: list[Callable[[RolUsuario], None]] = [
    puntos_de_venta._exigir_administrador,
    reembolsos_comunes.exigir_administrador,
    recursos._exigir_administrador,
    reglas._exigir_administrador,
    plantillas.exigir_administrador,
    faqs._exigir_administrador,
    paquete._exigir_administrador,
    lambda rol: vinculos._exigir_administrador(rol, "sin permiso"),
]


@pytest.mark.parametrize("guardia", GUARDIAS_DE_GESTOR)
def test_solo_lectura_no_gestiona_y_es_un_403(guardia: Callable[[RolUsuario], None]) -> None:
    with pytest.raises(OperacionNoPermitida):
        guardia(RolUsuario.SOLO_LECTURA)


@pytest.mark.parametrize("guardia", GUARDIAS_DE_ADMINISTRADOR)
@pytest.mark.parametrize("rol", [RolUsuario.OPERADOR, RolUsuario.SOLO_LECTURA])
def test_lo_de_administrador_rechaza_a_los_demas_con_403(
    guardia: Callable[[RolUsuario], None], rol: RolUsuario
) -> None:
    with pytest.raises(OperacionNoPermitida):
        guardia(rol)


def test_la_bitacora_negada_tambien_es_un_403() -> None:
    assert issubclass(AccesoALaBitacoraDenegado, OperacionNoPermitida)


def test_operacion_no_permitida_se_responde_403() -> None:
    assert CODIGOS[OperacionNoPermitida] == status.HTTP_403_FORBIDDEN
