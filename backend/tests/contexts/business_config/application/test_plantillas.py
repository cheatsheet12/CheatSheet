"""Las plantillas de fábrica y su siembra (U6, casos 3 y 4): sin red, sin base."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cheatsheet.contexts.business_config.application.plantillas import (
    DE_FABRICA,
    IDIOMA_POR_DEFECTO,
    ListarPlantillas,
)
from cheatsheet.contexts.business_config.domain.plantilla import (
    EstadoDeAprobacion,
    empieza_o_termina_con_variable,
)
from cheatsheet.contexts.business_config.domain.regla import CanalNotificacion
from cheatsheet.shared.empresa import EmpresaId

from .dobles_plantillas import RepositorioPlantillasEnMemoria

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 10, 6, 15, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())


@pytest.mark.parametrize("codigo", sorted(DE_FABRICA))
async def test_ningun_texto_de_fabrica_de_whatsapp_empieza_ni_termina_con_variable(
    codigo: str,
) -> None:
    """Caso 3: Meta rechaza esas plantillas, así que no pueden ser las de fábrica."""
    canal, cuerpo = DE_FABRICA[codigo]

    if canal is CanalNotificacion.WHATSAPP:
        assert not empieza_o_termina_con_variable(cuerpo), cuerpo


async def test_los_dos_textos_de_cobro_terminan_en_gracias() -> None:
    assert DE_FABRICA["recordatorio_de_cobro"][1].endswith("{{link}} Gracias.")
    assert DE_FABRICA["cobro_generado"][1].endswith("{{link}} Gracias.")


async def test_el_listado_siembra_las_seis_sin_enviar_con_el_codigo_como_nombre() -> None:
    plantillas = RepositorioPlantillasEnMemoria()

    listadas = await ListarPlantillas(plantillas).ejecutar(empresa_id=EMPRESA, ahora=AHORA)

    assert [una.codigo for una in listadas] == sorted(DE_FABRICA)
    for una in listadas:
        assert una.estado_aprobacion is EstadoDeAprobacion.SIN_ENVIAR
        assert una.nombre_en_meta == una.codigo
        assert una.idioma == IDIOMA_POR_DEFECTO
        assert una.meta_plantilla_id is None
        assert not una.puede_usarse


async def test_sembrar_dos_veces_no_duplica() -> None:
    plantillas = RepositorioPlantillasEnMemoria()
    caso = ListarPlantillas(plantillas)

    await caso.ejecutar(empresa_id=EMPRESA, ahora=AHORA)
    segunda = await caso.ejecutar(empresa_id=EMPRESA, ahora=AHORA)

    assert len(segunda) == len(DE_FABRICA)
    assert len(plantillas.filas) == len(DE_FABRICA)
