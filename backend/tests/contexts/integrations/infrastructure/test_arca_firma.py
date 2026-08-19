"""La credencial fiscal y la firma CMS — casos 1 a 5 del plan.

Criptografía pura: no hay red, no hay dobles y no hay archivos fijos. Cada test genera el
certificado que necesita, que es también la única forma de tener uno **vencido** sin
esperar dos años ni commitear una credencial (`CLAUDE.md` §3.3).

Lo que se prueba acá es lo que ADR-0004 apostó: que `cryptography` alcanza y que PyAfipWs
no hace falta.
"""

from __future__ import annotations

import datetime as dt

import pytest
from cheatsheet.contexts.integrations.application.errors import ConexionRechazada
from cheatsheet.contexts.integrations.domain.ticket import ServicioDeArca
from cheatsheet.contexts.integrations.infrastructure.arca import firma
from cryptography.hazmat.primitives.serialization import pkcs7
from defusedxml.ElementTree import fromstring as parsear_xml

from tests.contexts.integrations.conftest_arca import (
    CUIT_DE_PRUEBA,
    TITULAR_DE_PRUEBA,
    bundle,
    bundle_con_clave_ajena,
    certificado_y_clave,
)

AHORA = dt.datetime(2026, 8, 19, 12, 0, tzinfo=dt.UTC)


# ------------------------------------------------------------------ casos 1, 2 y 3


def test_el_bundle_se_parsea_en_certificado_y_clave() -> None:
    """Caso 1. Los dos archivos viajan juntos porque todo lo secreto va cifrado."""
    credencial = firma.leer_credencial(bundle())

    assert credencial.cuit == CUIT_DE_PRUEBA
    assert credencial.titular == TITULAR_DE_PRUEBA
    assert credencial.vence_en > dt.datetime.now(dt.UTC)


def test_una_clave_que_no_es_del_certificado_se_rechaza() -> None:
    """Caso 2. Es el error clásico al armar el par, y ARCA lo devolvería como un fallo
    genérico de CMS que suena a «tu certificado no está autorizado» — mandando al
    Administrador a preguntarle a ARCA por un problema que está de este lado."""
    with pytest.raises(ConexionRechazada) as fallo:
        firma.leer_credencial(bundle_con_clave_ajena())

    assert "no corresponde" in str(fallo.value)


def test_un_certificado_sin_clave_se_rechaza() -> None:
    pem, _ = certificado_y_clave()

    with pytest.raises(ConexionRechazada) as fallo:
        firma.leer_credencial(pem)

    assert "clave privada" in str(fallo.value)


def test_un_archivo_que_no_es_pem_se_rechaza() -> None:
    with pytest.raises(ConexionRechazada) as fallo:
        firma.leer_credencial(b"esto no es un certificado")

    assert "certificado" in str(fallo.value)


def test_un_certificado_vencido_se_rechaza_sin_llamar_a_arca() -> None:
    """Caso 3. Verificable localmente, así que no hay razón para molestar a ARCA."""
    credencial = firma.leer_credencial(bundle(vence_en_dias=-1))

    with pytest.raises(ConexionRechazada) as fallo:
        firma.exigir_vigente(credencial, dt.datetime.now(dt.UTC))

    assert "vencio" in str(fallo.value)


def test_un_certificado_vigente_pasa_la_verificacion_local() -> None:
    credencial = firma.leer_credencial(bundle(vence_en_dias=30))

    firma.exigir_vigente(credencial, dt.datetime.now(dt.UTC))


def test_un_certificado_sin_cuit_no_rompe_nada() -> None:
    """Un campo de presentación ausente no puede bloquear una conexión válida."""
    credencial = firma.leer_credencial(bundle(cuit=""))

    assert credencial.cuit == ""
    assert credencial.titular == TITULAR_DE_PRUEBA


# ------------------------------------------------------------------ casos 4 y 5


def test_la_solicitud_lleva_el_servicio_y_la_ventana_temporal() -> None:
    """Caso 5. ARCA rechaza una ventana que considere irrazonable."""
    documento = firma.armar_solicitud(ServicioDeArca.WSFE, AHORA)

    raiz = parsear_xml(documento)
    assert raiz.findtext("service") == "wsfe"
    generacion = dt.datetime.fromisoformat(raiz.findtext(".//generationTime") or "")
    expiracion = dt.datetime.fromisoformat(raiz.findtext(".//expirationTime") or "")
    assert generacion < AHORA < expiracion
    assert raiz.findtext(".//uniqueId")


def test_dos_solicitudes_no_comparten_unique_id() -> None:
    """Un contador que se reinicia con el proceso choca consigo mismo."""
    identificadores = {
        parsear_xml(firma.armar_solicitud(ServicioDeArca.WSFE, AHORA)).findtext(".//uniqueId")
        for _ in range(20)
    }

    assert len(identificadores) > 1


def test_el_servicio_del_padron_tambien_se_puede_pedir() -> None:
    """La unidad siguiente usa el mismo mecanismo con otro nombre de servicio."""
    documento = firma.armar_solicitud(ServicioDeArca.PADRON_A5, AHORA)

    assert parsear_xml(documento).findtext("service") == "ws_sr_padron_a5"


def test_la_firma_produce_un_cms_der_que_lleva_el_certificado() -> None:
    """Caso 4. Esto es lo que ADR-0004 apostó: `cryptography` alcanza, sin PyAfipWs.

    Se verifica que el blob sea CMS de verdad —parseable, con el certificado del firmante
    adentro— y no sólo que la llamada no explote.
    """
    credencial = firma.leer_credencial(bundle())
    solicitud = firma.armar_solicitud(ServicioDeArca.WSFE, AHORA)

    cms = firma.firmar(solicitud, credencial)

    certificados = pkcs7.load_der_pkcs7_certificates(cms)
    assert len(certificados) == 1
    assert certificados[0].subject == credencial.certificado.subject


def test_dos_firmas_de_la_misma_credencial_son_verificables() -> None:
    """Firmar no muta la credencial: se usa una vez por ticket y hay varios por empresa."""
    credencial = firma.leer_credencial(bundle())

    for _ in range(2):
        cms = firma.firmar(firma.armar_solicitud(ServicioDeArca.WSFE, AHORA), credencial)
        assert pkcs7.load_der_pkcs7_certificates(cms)
