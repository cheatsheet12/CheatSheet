"""`AvisoDePagoPorWhatsApp`: el aviso de cobro confirmado por el canal de la empresa (HU-E8-04 RN-01).

El canal y las plantillas son dobles: **ningún test toca la red**. Lo que se afirma es el texto de
fábrica (con el monto en `Decimal` y `ROUND_HALF_UP`), que una plantilla aprobada gana, que se
pide con las variables que la plantilla `cobro_pagado` admite, y que ningún log lleva datos
personales.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.payments.application.ports_envio import DatosDeAvisoDePago
from cheatsheet.contexts.payments.infrastructure.avisos import (
    CODIGO_COBRO_PAGADO,
    AvisoDePagoPorWhatsApp,
    EnvioParaAviso,
    ResultadoLocal,
    texto_de_aviso_de_pago,
    variables_de_aviso_de_pago,
)
from structlog.testing import capture_logs

pytestmark = pytest.mark.asyncio

TELEFONO = "5491155550000"
NOMBRE = "Rosa Diaz"


def _datos(monto: str = "12500.00") -> DatosDeAvisoDePago:
    return DatosDeAvisoDePago(
        cobro_id=uuid4(),
        cliente_id=uuid4(),
        nombre=NOMBRE,
        telefono=TELEFONO,
        concepto="Cuota de octubre",
        monto=Decimal(monto),
    )


class CanalFalso:
    def __init__(self, resultado: ResultadoLocal | None = None) -> None:
        self._resultado = resultado or ResultadoLocal(enviado=True)
        self.envios: list[tuple[UUID, str, EnvioParaAviso]] = []

    async def notificar(
        self, *, cliente_id: UUID, telefono: str, envio: EnvioParaAviso
    ) -> ResultadoLocal:
        self.envios.append((cliente_id, telefono, envio))
        return self._resultado


class PlantillaAprobada:
    nombre_en_meta = "cobro_pagado"
    idioma = "es_AR"
    texto = "Hola Rosa Diaz, recibimos tu pago de Cuota de octubre por $ 12.500,00. Gracias."

    def __init__(self) -> None:
        self.parametros = {
            "nombre": NOMBRE,
            "concepto": "Cuota de octubre",
            "monto": "12.500,00",
        }


class PlantillasFalsas:
    def __init__(self, plantilla: PlantillaAprobada | None = None) -> None:
        self._plantilla = plantilla
        self.pedidas: list[tuple[str, Mapping[str, str]]] = []

    async def para(self, codigo: str, variables: Mapping[str, str]) -> PlantillaAprobada | None:
        self.pedidas.append((codigo, dict(variables)))
        return self._plantilla


async def test_sin_plantilla_aprobada_sale_el_texto_de_fabrica() -> None:
    datos, canal = _datos(), CanalFalso()

    await AvisoDePagoPorWhatsApp(canal, PlantillasFalsas()).avisar(datos)

    ((cliente_id, telefono, envio),) = canal.envios
    assert (cliente_id, telefono) == (datos.cliente_id, TELEFONO)
    assert envio.plantilla is None
    assert envio.texto == (
        "Hola Rosa Diaz, recibimos tu pago de Cuota de octubre por $ 12.500,00. ¡Gracias!"
    )


async def test_con_plantilla_aprobada_sale_como_plantilla_con_su_cuerpo_resuelto() -> None:
    canal, plantillas = CanalFalso(), PlantillasFalsas(PlantillaAprobada())

    await AvisoDePagoPorWhatsApp(canal, plantillas).avisar(_datos())

    ((_, _, envio),) = canal.envios
    assert envio.texto == PlantillaAprobada.texto
    assert envio.plantilla is not None
    assert (envio.plantilla.nombre, envio.plantilla.idioma) == ("cobro_pagado", "es_AR")
    assert dict(envio.plantilla.parametros) == PlantillaAprobada().parametros


async def test_la_plantilla_se_pide_por_su_codigo_y_con_sus_variables() -> None:
    plantillas = PlantillasFalsas()

    await AvisoDePagoPorWhatsApp(CanalFalso(), plantillas).avisar(_datos())

    assert plantillas.pedidas == [
        (
            CODIGO_COBRO_PAGADO,
            {"nombre": NOMBRE, "concepto": "Cuota de octubre", "monto": "12.500,00"},
        )
    ]
    assert CODIGO_COBRO_PAGADO == "cobro_pagado"


@pytest.mark.parametrize(
    ("monto", "esperado"),
    [
        ("1234.565", "1.234,57"),  # ROUND_HALF_UP: la mitad sube
        ("10.004", "10,00"),
        ("0.01", "0,01"),
        ("1234567.80", "1.234.567,80"),
    ],
)
async def test_monto_del_aviso_redondea_half_up_en_formato_argentino(
    monto: str, esperado: str
) -> None:
    datos = _datos(monto)

    assert variables_de_aviso_de_pago(datos)["monto"] == esperado
    assert f"por $ {esperado}." in texto_de_aviso_de_pago(datos)


async def test_una_falla_del_canal_queda_en_el_log_sin_datos_personales() -> None:
    canal = CanalFalso(ResultadoLocal(enviado=False, falla="131047"))

    with capture_logs() as registros:
        await AvisoDePagoPorWhatsApp(canal, PlantillasFalsas()).avisar(_datos())

    (registro,) = registros
    assert (registro["event"], registro["causa"]) == ("aviso_de_pago_fallido", "131047")
    assert TELEFONO not in str(registros)
    assert NOMBRE not in str(registros)


async def test_un_aviso_enviado_que_no_se_pudo_guardar_se_registra() -> None:
    canal = CanalFalso(ResultadoLocal(enviado=True, sin_registrar=True, causa="OperationalError"))

    with capture_logs() as registros:
        await AvisoDePagoPorWhatsApp(canal, PlantillasFalsas()).avisar(_datos())

    (registro,) = registros
    assert (registro["event"], registro["causa"]) == (
        "aviso_de_pago_sin_registrar",
        "OperationalError",
    )
