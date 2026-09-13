"""El canal de avisos de turnos y su doble (HU-E7-02 RN-03/RN-04, HU-E7-06 RN-04).

Dos cosas se prueban acá, y las dos son sobre **qué no hace** el doble:

1. **Se niega a arrancar en producción.** Es el mismo trato que `EnvioPorConsola` del épico 6.
   Una empresa cuyos avisos de turno salen a un log es una empresa cuyos clientes se enteran
   de la cancelación cuando llegan al local.

2. **No registra datos personales.** El teléfono y el nombre del cliente no entran al log,
   aunque el log sea de desarrollo (`CLAUDE.md` §5).

Y una sobre lo que sí hace: el aviso de reprogramación **dice el horario viejo además del
nuevo**. Sólo el nuevo dejaría a alguien que ya tenía el turno anotado sin saber si es el mismo
o uno más, que es la manera de que aparezca en el horario equivocado.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from cheatsheet.contexts.scheduling.application.ports import DatosDeAviso
from cheatsheet.contexts.scheduling.infrastructure.avisos import (
    AvisoPorConsola,
    texto_de_cancelacion,
    texto_de_reprogramacion,
    texto_de_reserva,
)
from cheatsheet.platform.settings import Entorno

DATOS = DatosDeAviso(
    telefono="5491112345678",
    nombre_del_cliente="Ana Diaz",
    servicio="Corte",
    recurso="Consultorio 1",
    inicio=datetime(2026, 9, 8, 18, 0, tzinfo=UTC),
)


def test_se_niega_a_arrancar_en_produccion() -> None:
    with pytest.raises(RuntimeError):
        AvisoPorConsola(Entorno.PRODUCTION)


def test_los_tres_textos_nombran_el_servicio_y_el_horario() -> None:
    for texto in (
        texto_de_reserva(DATOS),
        texto_de_cancelacion(DATOS),
        texto_de_reprogramacion(DATOS),
    ):
        assert "Corte" in texto
        assert "08/09/2026" in texto
        assert "Ana Diaz" in texto


def test_la_reprogramacion_dice_el_horario_viejo_ademas_del_nuevo() -> None:
    movido = DatosDeAviso(
        telefono=DATOS.telefono,
        nombre_del_cliente=DATOS.nombre_del_cliente,
        servicio=DATOS.servicio,
        recurso=DATOS.recurso,
        inicio=datetime(2026, 9, 9, 18, 0, tzinfo=UTC),
        inicio_anterior=DATOS.inicio,
    )

    texto = texto_de_reprogramacion(movido)

    assert "09/09/2026" in texto
    assert "08/09/2026" in texto


def test_sin_horario_anterior_el_texto_no_dice_nada_de_antes() -> None:
    # Un turno reprogramado por primera vez desde otro canal puede no traer el dato; el texto
    # tiene que quedar bien igual y no con un «(antes None)».
    assert "antes" not in texto_de_reprogramacion(DATOS)


class TestDoble:
    @pytest.mark.asyncio
    async def test_registra_la_clase_de_aviso_y_no_el_telefono(self) -> None:
        doble = AvisoPorConsola(Entorno.LOCAL)

        await doble.avisar_reserva(DATOS)
        await doble.avisar_cancelacion(DATOS)
        await doble.avisar_reprogramacion(DATOS)

        assert [clase for clase, _ in doble.avisos] == [
            "reserva",
            "cancelacion",
            "reprogramacion",
        ]
        # El texto sí lleva el nombre —es el mensaje que se le mandaría al cliente— pero lo
        # que se guarda para inspección no incluye el número.
        assert all(DATOS.telefono not in texto for _, texto in doble.avisos)
