"""Reading the fiscal credential and signing a login ticket request.

Pure cryptography: everything here runs in-process, opens no socket and is testable with a
certificate generated inside the test.

**No PyAfipWs — decision D-d, recorded in ADR-0004.** The Etapa 5 documents named that
library for ARCA, and it stays named for WSFEv1 in epic 5. For WSAA the whole job is one
fifteen-line XML document signed once as CMS/PKCS#7, which `cryptography` does natively
and in-process. PyAfipWs performs the same signature by shelling out to the `openssl`
binary or through M2Crypto depending on version — a private key on a command line, or a C
extension we do not otherwise carry, in exchange for nothing.

**The private key never leaves this process and never reaches a log.** It arrives
decrypted from `integrations`' own cipher (ADR-0003 point 3), is used to sign, and is
dropped with the frame.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from xml.etree import ElementTree

from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID

from cheatsheet.contexts.integrations.application.errors import ConexionRechazada
from cheatsheet.contexts.integrations.domain.ticket import ServicioDeArca

#: How long the request itself is valid. ARCA rejects a window it considers unreasonable,
#: and a wide one is a replay window; ten minutes each way absorbs ordinary clock skew.
MARGEN_DE_RELOJ = timedelta(minutes=10)


@dataclass(frozen=True, slots=True)
class CredencialFiscal:
    """A company's certificate and the private key that goes with it.

    Held together because one without the other is useless, and validated together for the
    same reason: a certificate paired with somebody else's key produces a signature ARCA
    rejects with a message that says nothing about the real cause.
    """

    certificado: x509.Certificate
    #: Narrowed to what CMS can actually sign with. ARCA issues RSA certificates; the
    #: check happens at load time so an unsupported key is a clear message instead of a
    #: `TypeError` from deep inside the signer.
    clave: pkcs7.PKCS7PrivateKeyTypes

    @property
    def vence_en(self) -> datetime:
        """The certificate's own `notAfter`. Readable without asking ARCA anything.

        This is what lets the daily sweep and the on-screen check answer "is this still
        valid?" at zero cost and without burning an access ticket.
        """
        return self.certificado.not_valid_after_utc

    @property
    def titular(self) -> str:
        """The subject's common name, for the card. Usually the company's fiscal name."""
        atributos = self.certificado.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        return str(atributos[0].value) if atributos else ""

    @property
    def cuit(self) -> str:
        """The CUIT ARCA put in the subject's serialNumber, as `CUIT 20123456789`.

        Returned bare when it is not there rather than raising: the certificate is still
        usable, and a missing display field must not block a connection.
        """
        atributos = self.certificado.subject.get_attributes_for_oid(NameOID.SERIAL_NUMBER)
        if not atributos:
            return ""
        crudo = str(atributos[0].value)
        return crudo.removeprefix("CUIT ").strip()


def leer_credencial(bundle: bytes) -> CredencialFiscal:
    """Parse the PEM bundle the Administrator uploaded: certificate plus private key.

    One blob and not two fields because everything that is secret has to travel through
    `contenido`, which is what gets encrypted. `parametros` is plain JSONB — a private key
    there would be a private key in the clear.
    """
    try:
        certificado = x509.load_pem_x509_certificate(bundle)
    except (ValueError, TypeError) as exc:
        raise ConexionRechazada(
            "No se pudo leer el certificado. Tiene que ser un archivo PEM de ARCA"
        ) from exc
    try:
        clave = serialization.load_pem_private_key(bundle, password=None)
    except TypeError as exc:
        raise ConexionRechazada(
            "La clave privada esta protegida con contrasena y no se puede usar asi"
        ) from exc
    except (ValueError, UnsupportedAlgorithm) as exc:
        # `UnsupportedAlgorithm` does not derive from `ValueError`, so it needs naming:
        # it is what `cryptography` raises for a key type it cannot load.
        raise ConexionRechazada(
            "No se pudo leer la clave privada. Tiene que ser un archivo PEM sin cifrar"
        ) from exc

    if not isinstance(clave, (rsa.RSAPrivateKey, ec.EllipticCurvePrivateKey)):
        raise ConexionRechazada(
            "El tipo de clave privada no sirve para firmar contra ARCA. Tiene que ser RSA"
        )
    credencial = CredencialFiscal(certificado=certificado, clave=clave)
    _exigir_que_la_clave_sea_del_certificado(credencial)
    return credencial


def _exigir_que_la_clave_sea_del_certificado(credencial: CredencialFiscal) -> None:
    """Checked here, not left to ARCA.

    A mismatched pair produces a signature WSAA rejects with a generic CMS error, which
    reads like "your certificate is not authorised" and sends the Administrator to ask
    ARCA about a problem that is on this side.
    """
    formato = serialization.PublicFormat.SubjectPublicKeyInfo
    codificacion = serialization.Encoding.DER
    # Compared as serialized bytes rather than as numbers: it works for every key type
    # without a branch per algorithm, and two keys with the same DER are the same key.
    del_certificado = credencial.certificado.public_key().public_bytes(codificacion, formato)
    de_la_clave = credencial.clave.public_key().public_bytes(codificacion, formato)
    if del_certificado != de_la_clave:
        raise ConexionRechazada("La clave privada no corresponde a este certificado")


def exigir_vigente(credencial: CredencialFiscal, ahora: datetime) -> None:
    """An expired certificate is rejected before a single byte reaches ARCA."""
    if credencial.vence_en <= ahora:
        raise ConexionRechazada(
            f"El certificado vencio el {credencial.vence_en.date().isoformat()}. "
            f"Renovalo en ARCA y volve a cargarlo"
        )


def armar_solicitud(servicio: ServicioDeArca, ahora: datetime) -> bytes:
    """The `loginTicketRequest` document, built with the stdlib XML writer.

    `uniqueId` is random rather than a counter: ARCA uses it to tell one request from
    another, and a counter that resets when the process restarts collides with itself.
    """
    raiz = ElementTree.Element("loginTicketRequest", version="1.0")
    cabecera = ElementTree.SubElement(raiz, "header")
    ElementTree.SubElement(cabecera, "uniqueId").text = str(secrets.randbelow(2**31 - 1))
    ElementTree.SubElement(cabecera, "generationTime").text = _instante(ahora - MARGEN_DE_RELOJ)
    ElementTree.SubElement(cabecera, "expirationTime").text = _instante(ahora + MARGEN_DE_RELOJ)
    ElementTree.SubElement(raiz, "service").text = servicio.value
    documento: bytes = ElementTree.tostring(raiz, encoding="utf-8", xml_declaration=True)
    return documento


def firmar(solicitud: bytes, credencial: CredencialFiscal) -> bytes:
    """Sign the request as a CMS/PKCS#7 blob in DER, which is what `LoginCms` expects.

    `Binary` keeps the content as-is; without it the signer would apply MIME canonical
    line endings and ARCA would receive a document whose signature does not verify.
    """
    return (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(solicitud)
        .add_signer(credencial.certificado, credencial.clave, hashes.SHA256())
        .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.Binary])
    )


def _instante(momento: datetime) -> str:
    """ARCA wants ISO-8601 with an offset, seconds resolution."""
    return momento.replace(microsecond=0).isoformat()
