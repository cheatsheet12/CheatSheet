"""`AvisoPorWhatsApp` con la plantilla aprobada de Meta (U6, casos 22 y 23).

Tres avisos —reserva, cancelación y reprogramación— usan su código de plantilla
(`turno_confirmado`, `turno_cancelado`, `turno_reprogramado`). `recordatorio_de_turno` existe en el
catálogo pero lo manda U8, no este adaptador. Sin plantilla aprobada sale el texto de fábrica de
siempre. Sin red: el canal y las plantillas son dobles.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from cheatsheet.contexts.scheduling.application.ports import DatosDeAviso
from cheatsheet.contexts.scheduling.infrastructure.avisos import (
    AvisoPorWhatsApp,
    texto_de_cancelacion,
    texto_de_reprogramacion,
    texto_de_reserva,
)

pytestmark = pytest.mark.asyncio

TELEFONO = "5491112345678"
NOMBRE = "Ana Diaz"

# 13:30 UTC es 10:30 en Buenos Aires (UTC-3, sin horario de verano).
DATOS = DatosDeAviso(
    telefono=TELEFONO,
    nombre_del_cliente=NOMBRE,
    servicio="Corte",
    recurso="Consultorio 1",
    inicio=datetime(2026, 10, 15, 13, 30, tzinfo=UTC),
)
MOVIDO = DatosDeAviso(
    telefono=TELEFONO,
    nombre_del_cliente=NOMBRE,
    servicio="Corte",
    recurso="Consultorio 1",
    inicio=datetime(2026, 10, 15, 13, 30, tzinfo=UTC),
    inicio_anterior=datetime(2026, 10, 14, 12, 0, tzinfo=UTC),
)


@dataclass(frozen=True)
class _Aprobada:
    nombre_en_meta: str
    idioma: str
    parametros: Mapping[str, str]


class PlantillasFalsas:
    def __init__(self, *aprobadas: str) -> None:
        self._aprobadas = set(aprobadas)
        self.pedidos: list[tuple[str, dict[str, str]]] = []

    async def para(self, codigo: str, variables: Mapping[str, str]) -> _Aprobada | None:
        self.pedidos.append((codigo, dict(variables)))
        if codigo not in self._aprobadas:
            return None
        return _Aprobada(nombre_en_meta=codigo, idioma="es_AR", parametros=dict(variables))


class CanalGrabador:
    def __init__(self, *, falla: Exception | None = None) -> None:
        self.textos: list[tuple[str, str]] = []
        self.plantillas: list[tuple[str, str, str, dict[str, str]]] = []
        self._falla = falla

    async def enviar(self, *, telefono: str, texto: str) -> str:
        if self._falla is not None:
            raise self._falla
        self.textos.append((telefono, texto))
        return "wamid.TEXTO"

    async def enviar_plantilla(
        self, *, telefono: str, nombre: str, idioma: str, parametros: Mapping[str, str]
    ) -> str:
        if self._falla is not None:
            raise self._falla
        self.plantillas.append((telefono, nombre, idioma, dict(parametros)))
        return "wamid.PLANTILLA"


TODAS = ("turno_confirmado", "turno_cancelado", "turno_reprogramado")


async def test_los_tres_avisos_usan_su_codigo_de_plantilla() -> None:
    """Caso 22."""
    canal = CanalGrabador()
    aviso = AvisoPorWhatsApp(canal, PlantillasFalsas(*TODAS))

    await aviso.avisar_reserva(DATOS)
    await aviso.avisar_cancelacion(DATOS)
    await aviso.avisar_reprogramacion(MOVIDO)

    assert [nombre for _, nombre, _, _ in canal.plantillas] == list(TODAS)
    assert canal.textos == []
    assert {telefono for telefono, _, _, _ in canal.plantillas} == {TELEFONO}
    assert {idioma for _, _, idioma, _ in canal.plantillas} == {"es_AR"}


async def test_fecha_y_hora_salen_por_separado_y_en_hora_argentina() -> None:
    """Caso 22: `2026-10-15T13:30Z` → «15/10/2026» y «10:30» (la conversión la prueba U5, caso 33)."""
    plantillas = PlantillasFalsas(*TODAS)

    await AvisoPorWhatsApp(CanalGrabador(), plantillas).avisar_reserva(DATOS)

    (pedido,) = plantillas.pedidos
    assert pedido == (
        "turno_confirmado",
        {
            "nombre": NOMBRE,
            "servicio": "Corte",
            "recurso": "Consultorio 1",
            "fecha": "15/10/2026",
            "hora": "10:30",
        },
    )


async def test_la_reprogramacion_lleva_tambien_el_horario_anterior_separado() -> None:
    plantillas = PlantillasFalsas(*TODAS)

    await AvisoPorWhatsApp(CanalGrabador(), plantillas).avisar_reprogramacion(MOVIDO)

    (_, variables) = plantillas.pedidos[0]
    assert (variables["fecha"], variables["hora"]) == ("15/10/2026", "10:30")
    assert (variables["fecha_anterior"], variables["hora_anterior"]) == ("14/10/2026", "09:00")


async def test_una_reprogramacion_sin_horario_anterior_no_inventa_las_variables_de_antes() -> None:
    plantillas = PlantillasFalsas()

    await AvisoPorWhatsApp(CanalGrabador(), plantillas).avisar_reprogramacion(DATOS)

    (_, variables) = plantillas.pedidos[0]
    assert "fecha_anterior" not in variables
    assert "hora_anterior" not in variables


async def test_cerca_de_medianoche_el_dia_tambien_se_convierte() -> None:
    plantillas = PlantillasFalsas()
    tarde = DatosDeAviso(
        telefono=TELEFONO,
        nombre_del_cliente=NOMBRE,
        servicio="Corte",
        recurso="Consultorio 1",
        inicio=datetime(2026, 10, 16, 2, 30, tzinfo=UTC),
    )

    await AvisoPorWhatsApp(CanalGrabador(), plantillas).avisar_reserva(tarde)

    (_, variables) = plantillas.pedidos[0]
    assert (variables["fecha"], variables["hora"]) == ("15/10/2026", "23:30")


async def test_sin_plantilla_aprobada_sale_el_texto_de_fabrica_de_cada_aviso() -> None:
    canal = CanalGrabador()
    aviso = AvisoPorWhatsApp(canal, PlantillasFalsas())

    await aviso.avisar_reserva(DATOS)
    await aviso.avisar_cancelacion(DATOS)
    await aviso.avisar_reprogramacion(MOVIDO)

    assert canal.plantillas == []
    assert [texto for _, texto in canal.textos] == [
        texto_de_reserva(DATOS),
        texto_de_cancelacion(DATOS),
        texto_de_reprogramacion(MOVIDO),
    ]


async def test_solo_la_aprobada_sale_como_plantilla_y_las_demas_como_texto() -> None:
    canal = CanalGrabador()
    aviso = AvisoPorWhatsApp(canal, PlantillasFalsas("turno_cancelado"))

    await aviso.avisar_reserva(DATOS)
    await aviso.avisar_cancelacion(DATOS)

    assert [nombre for _, nombre, _, _ in canal.plantillas] == ["turno_cancelado"]
    assert [texto for _, texto in canal.textos] == [texto_de_reserva(DATOS)]


async def test_un_fallo_de_la_plantilla_no_levanta() -> None:
    aviso = AvisoPorWhatsApp(
        CanalGrabador(falla=RuntimeError(f"falló {TELEFONO} {NOMBRE}")), PlantillasFalsas(*TODAS)
    )

    await aviso.avisar_reserva(DATOS)
    await aviso.avisar_cancelacion(DATOS)
    await aviso.avisar_reprogramacion(MOVIDO)
