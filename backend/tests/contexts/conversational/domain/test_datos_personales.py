"""`ocultar_datos_personales` e `historial_para_el_interprete` (T11, `CLAUDE.md` §3.6).

**Ningún dato personal real viaja al modelo sin ocultarse.** La regla es conservadora en un
sentido y precisa en otro: oculta cualquier secuencia de siete o más dígitos (teléfono, DNI,
CUIT/CUIL, CBU/CVU, tarjeta) aunque tenga puntos, guiones o espacios, y deja pasar lo que el agente
necesita entender: horas, fechas y el «2» de «el 2».
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cheatsheet.contexts.conversational.domain.conversacion import (
    DireccionMensaje,
    Mensaje,
    OrigenDelMensaje,
    TipoContenido,
)
from cheatsheet.contexts.conversational.domain.datos_personales import (
    DATO_OCULTO,
    DESCRIPTOR_DEL_OPERADOR,
    DESCRIPTOR_DEL_SISTEMA,
    historial_para_el_interprete,
    ocultar_datos_personales,
)
from cheatsheet.shared.empresa import EmpresaId

AHORA = datetime(2026, 10, 5, 15, 0, tzinfo=UTC)


class TestOcultar:
    @pytest.mark.parametrize(
        "texto",
        [
            "ana.perez@gmail.com",
            "11 5555-1234",
            "mi dni es 30.123.456",
            "20-12345678-9",
            "0170099220000067890123",
            "4509 9535 6623 3704",
            "+54 9 11 5555 1234",
        ],
    )
    def test_oculta(self, texto: str) -> None:
        resultado = ocultar_datos_personales(texto)

        assert DATO_OCULTO in resultado
        assert not any(cuatro in resultado for cuatro in ("5555", "30.123", "12345678", "3704"))
        assert "@" not in resultado

    @pytest.mark.parametrize(
        "texto",
        [
            "quiero un turno a las 10:30",
            "para el 14/10",
            "el 2",
            "a las 17 hs",
            "el 14 de octubre a las 10.30",
            "opción 3",
            "el año 2026",
        ],
    )
    def test_deja_pasar_horas_fechas_y_ordinales(self, texto: str) -> None:
        assert ocultar_datos_personales(texto) == texto

    def test_oculta_solo_el_dato_y_conserva_el_resto(self) -> None:
        assert (
            ocultar_datos_personales("llamame al 11 5555-1234 mañana")
            == f"llamame al {DATO_OCULTO} mañana"
        )

    def test_dos_datos_en_el_mismo_texto(self) -> None:
        resultado = ocultar_datos_personales("ana@x.com o 1155551234")

        assert resultado == f"{DATO_OCULTO} o {DATO_OCULTO}"


def mensaje(
    contenido: str, direccion: DireccionMensaje, origen: OrigenDelMensaje | None = None
) -> Mensaje:
    return Mensaje(
        id=uuid4(),
        conversacion_id=uuid4(),
        empresa_id=EmpresaId(uuid4()),
        direccion=direccion,
        tipo_contenido=TipoContenido.TEXTO,
        contenido=contenido,
        momento=AHORA,
        origen=origen,
    )


class TestHistorial:
    def test_reemplaza_al_operador_y_al_sistema_por_su_descriptor(self) -> None:
        mensajes = [
            mensaje("quiero un turno", DireccionMensaje.ENTRANTE),
            mensaje("Tengo estos horarios", DireccionMensaje.SALIENTE, OrigenDelMensaje.AGENTE),
            mensaje(
                "Hola, soy Marta, tu DNI es 30123456",
                DireccionMensaje.SALIENTE,
                OrigenDelMensaje.OPERADOR,
            ),
            mensaje(
                "Turno confirmado para Ana", DireccionMensaje.SALIENTE, OrigenDelMensaje.SISTEMA
            ),
        ]

        historial = historial_para_el_interprete(mensajes)

        assert historial == [
            "quiero un turno",
            "Tengo estos horarios",
            DESCRIPTOR_DEL_OPERADOR,
            DESCRIPTOR_DEL_SISTEMA,
        ]

    def test_oculta_los_datos_personales_de_cada_mensaje(self) -> None:
        mensajes = [mensaje("mi dni es 30123456", DireccionMensaje.ENTRANTE)]

        assert historial_para_el_interprete(mensajes) == [f"mi dni es {DATO_OCULTO}"]

    def test_se_queda_con_los_ultimos(self) -> None:
        mensajes = [mensaje(f"m{n}", DireccionMensaje.ENTRANTE) for n in range(10)]

        assert historial_para_el_interprete(mensajes, limite=3) == ["m7", "m8", "m9"]
