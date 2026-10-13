"""«Enviar a revisión»: reenviar una plantilla sin enviar o rechazada, sin tocar su texto (U6)."""

from __future__ import annotations

import pytest
from cheatsheet.contexts.business_config.domain.plantilla import (
    MENSAJE_BORDE_CON_VARIABLE,
    EstadoDeAprobacion,
)
from cheatsheet.shared.errors import EntradaInvalida

from .dobles_plantillas import RevisionDeMetaFalsa
from .escena_revision import (
    CUERPO_VIEJO,
    PENDIENTE,
    Escena,
    una_plantilla,
)

pytestmark = pytest.mark.asyncio

# --- Enviar a revisión sin editar el texto ----------------------------------------------------------------------


async def test_enviar_a_revision_una_sin_enviar_la_crea_con_su_cuerpo_actual() -> None:
    escena = Escena(una_plantilla(), RevisionDeMetaFalsa(respuestas=[PENDIENTE]))

    resultado = await escena.enviar()

    assert escena.revision.creaciones[0][2] == CUERPO_VIEJO
    assert resultado.estado_aprobacion is EstadoDeAprobacion.PENDIENTE
    assert [e.accion for e in escena.publicador.eventos] == ["enviar_plantilla_a_meta"]  # type: ignore[attr-defined]


async def test_enviar_a_revision_una_rechazada_con_id_la_edita_en_meta() -> None:
    escena = Escena(
        una_plantilla(EstadoDeAprobacion.RECHAZADA, meta_plantilla_id="meta-9", motivo_meta="SCAM"),
        RevisionDeMetaFalsa(respuestas=[PENDIENTE]),
    )

    resultado = await escena.enviar()

    assert escena.revision.ediciones[0][0] == "meta-9"
    assert resultado.estado_aprobacion is EstadoDeAprobacion.PENDIENTE
    assert resultado.motivo_meta is None


@pytest.mark.parametrize(
    "estado",
    [
        EstadoDeAprobacion.PENDIENTE,
        EstadoDeAprobacion.APROBADA,
        EstadoDeAprobacion.PAUSADA,
    ],
)
async def test_enviar_a_revision_solo_corresponde_a_sin_enviar_o_rechazada(
    estado: EstadoDeAprobacion,
) -> None:
    escena = Escena(una_plantilla(estado, meta_plantilla_id="meta-9"))

    with pytest.raises(EntradaInvalida, match="no necesita reenviarse"):
        await escena.enviar()

    assert escena.revision.creaciones == []
    assert escena.revision.ediciones == []


async def test_enviar_a_revision_un_cuerpo_viejo_que_termina_en_variable_se_rechaza() -> None:
    escena = Escena(una_plantilla(cuerpo="Pagá acá: {{fecha}}"))

    with pytest.raises(EntradaInvalida) as salida:
        await escena.enviar()

    assert str(salida.value) == MENSAJE_BORDE_CON_VARIABLE
    assert escena.revision.creaciones == []
