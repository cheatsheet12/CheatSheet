"""La traducción del vocabulario de Meta — casos 7 a 11 del plan.

Funciones puras sobre el JSON de Graph API, así que acá no hay ni socket ni doble: se le
pasa la respuesta tal cual Meta la manda y se mira qué sale.
"""

from __future__ import annotations

import pytest
from cheatsheet.contexts.integrations.domain.valores import CLAVE_ETIQUETA, EstadoDeConexion
from cheatsheet.contexts.integrations.infrastructure.whatsapp.mapeo import (
    CLAVE_CALIDAD,
    CLAVE_DISPLAY_NAME,
    CLAVE_NUMERO,
    interpretar,
    parametros_informados,
)

NUMERO = "+54 9 11 5555-0000"


def _payload(**cambios: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name_status": "APPROVED",
        "verified_name": "Panaderia Dona Rosa",
        "quality_rating": "GREEN",
        "display_phone_number": NUMERO,
        "code_verification_status": "VERIFIED",
    }
    base.update(cambios)
    return base


def test_un_numero_aprobado_queda_conectado_con_nombre_y_calidad() -> None:
    """Caso 7. RN-03: se registra el display name verificado y la calidad de la línea."""
    resultado = interpretar(_payload())

    assert resultado.estado is EstadoDeConexion.CONECTADO
    assert resultado.detalle is None
    assert resultado.parametros[CLAVE_DISPLAY_NAME] == "Panaderia Dona Rosa"
    assert resultado.parametros[CLAVE_CALIDAD] == "GREEN"
    assert resultado.parametros[CLAVE_NUMERO] == NUMERO


def test_un_numero_en_revision_queda_pendiente() -> None:
    """Caso 8. RN-02: entre 24 y 72 horas, y en ese lapso no es ni error ni éxito."""
    resultado = interpretar(_payload(name_status="PENDING_REVIEW"))

    assert resultado.estado is EstadoDeConexion.PENDIENTE
    assert resultado.detalle is not None
    assert "24" in resultado.detalle


def test_un_numero_rechazado_queda_no_conectado_con_el_motivo() -> None:
    """Caso 9. El tercer criterio de aceptación: se notifica el motivo."""
    resultado = interpretar(_payload(name_status="DECLINED"))

    assert resultado.estado is EstadoDeConexion.NO_CONECTADO
    assert resultado.detalle is not None
    assert "rechaz" in resultado.detalle.lower()


def test_una_verificacion_vencida_queda_no_conectada() -> None:
    """Caso 10."""
    resultado = interpretar(_payload(name_status="EXPIRED"))

    assert resultado.estado is EstadoDeConexion.NO_CONECTADO
    assert resultado.detalle is not None


@pytest.mark.parametrize(
    "crudo", ["ALGO_NUEVO", "", 42, None], ids=["nuevo", "vacio", "int", "nulo"]
)
def test_un_estado_desconocido_de_meta_no_rompe_nada(crudo: object) -> None:
    """Caso 11. Meta agrega valores a este enum sin avisar.

    Un `KeyError` acá sería una tarea de Beat que muere en silencio y una integración que
    se queda muda para siempre. `ATENCION` es visible, honesto, y no destruye nada.
    """
    resultado = interpretar(_payload(name_status=crudo))

    assert resultado.estado is EstadoDeConexion.ATENCION
    assert resultado.detalle is not None


def test_una_linea_calificada_en_rojo_es_atencion_aunque_este_aprobada() -> None:
    """Meta está por restringir la línea: eso es exactamente «degradada»."""
    resultado = interpretar(_payload(quality_rating="RED"))

    assert resultado.estado is EstadoDeConexion.ATENCION
    assert resultado.detalle is not None
    assert "calidad" in resultado.detalle.lower()


def test_una_linea_amarilla_sigue_conectada() -> None:
    """`YELLOW` se registra pero no alarma: no hay restricción todavía."""
    resultado = interpretar(_payload(quality_rating="YELLOW"))

    assert resultado.estado is EstadoDeConexion.CONECTADO
    assert resultado.parametros[CLAVE_CALIDAD] == "YELLOW"


def test_una_respuesta_parcial_no_borra_lo_que_no_informa() -> None:
    """El agregado fusiona, así que devolver `None` acá borraría datos buenos."""
    informados = parametros_informados({"name_status": "APPROVED"})

    assert informados == {}


def test_la_etiqueta_junta_el_nombre_verificado_y_el_numero() -> None:
    """Es lo único de `parametros` que sale por la API; los IDs de Meta no salen."""
    informados = parametros_informados(_payload())

    assert informados[CLAVE_ETIQUETA] == f"Panaderia Dona Rosa · {NUMERO}"


def test_sin_nombre_verificado_la_etiqueta_es_el_numero_solo() -> None:
    informados = parametros_informados(_payload(verified_name=""))

    assert informados[CLAVE_ETIQUETA] == NUMERO
