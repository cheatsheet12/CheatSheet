"""El hilo del panel muestra por qué falló un mensaje saliente (U7, D-U7-7).

`motivo_de_falla` (un código de Meta o una clase corta, nunca el texto del error) viaja con cada
mensaje para que el hilo lo traduzca debajo de un `FALLIDO`. Un mensaje que salió no lo trae.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from cheatsheet.api.routers.conversaciones import _a_mensaje
from cheatsheet.contexts.conversational.domain.conversacion import (
    DireccionMensaje,
    EstadoEntrega,
    Mensaje,
    OrigenDelMensaje,
    TipoContenido,
)
from cheatsheet.shared.empresa import EmpresaId


def _aviso(estado: EstadoEntrega, motivo: str | None) -> Mensaje:
    return Mensaje(
        id=uuid4(),
        conversacion_id=uuid4(),
        empresa_id=EmpresaId(uuid4()),
        direccion=DireccionMensaje.SALIENTE,
        tipo_contenido=TipoContenido.TEXTO,
        contenido="Tu turno fue cancelado",
        momento=datetime(2026, 10, 7, 15, 0, tzinfo=UTC),
        origen=OrigenDelMensaje.SISTEMA,
        estado_entrega=estado,
        motivo_de_falla=motivo,
    )


def test_un_aviso_fallido_expone_su_motivo() -> None:
    salida = _a_mensaje(_aviso(EstadoEntrega.FALLIDO, "131047"))

    assert (salida.estado_entrega, salida.motivo_de_falla) == ("FALLIDO", "131047")


def test_un_aviso_enviado_no_trae_motivo() -> None:
    assert _a_mensaje(_aviso(EstadoEntrega.ENVIADO, None)).motivo_de_falla is None
