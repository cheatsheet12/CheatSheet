"""Certificados de prueba, generados en el momento.

**No hay ni un certificado real en el repositorio, y no puede haberlo**: `CLAUDE.md` §3.3
prohíbe commitear `.pem`, `.key`, `.crt` y `.p12`, y un certificado fiscal de verdad es
exactamente la credencial que esta unidad existe para proteger.

Generarlos acá cuesta unas décimas de segundo por test y da algo que los archivos fijos no
darían: un certificado **vencido** o **por vencer** se construye moviendo una fecha, en vez
de esperar dos años o commitear uno caducado.
"""

from __future__ import annotations

import datetime as dt

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

CUIT_DE_PRUEBA = "20123456789"
TITULAR_DE_PRUEBA = "panaderia dona rosa"

#: 2048 rather than 4096: es lo que ARCA emite, y en una suite que genera un par por test
#: la diferencia de tiempo se nota.
BITS = 2048


def _clave() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=BITS)


def _pem_de_la_clave(clave: rsa.RSAPrivateKey) -> bytes:
    return clave.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )


def certificado_y_clave(
    *,
    vence_en_dias: int = 400,
    cuit: str = CUIT_DE_PRUEBA,
    titular: str = TITULAR_DE_PRUEBA,
    clave: rsa.RSAPrivateKey | None = None,
    desde: dt.datetime | None = None,
) -> tuple[bytes, rsa.RSAPrivateKey]:
    """Un certificado autofirmado con la forma que ARCA emite, y su clave.

    `vence_en_dias` puede ser negativo: así se construye un certificado ya vencido sin
    esperar ni falsear el reloj del sistema.

    `desde` importa cuando el test congela el reloj. Un certificado construido contra el
    reloj real y evaluado contra `RelojFijo` da lo contrario de lo esperado, y el test que
    lo descubrió pasó por creer que estaba probando otra cosa.
    """
    clave = clave or _clave()
    atributos = [x509.NameAttribute(NameOID.COMMON_NAME, titular)]
    if cuit:
        # ARCA pone el CUIT en el serialNumber del subject, con el prefijo `CUIT `.
        atributos.append(x509.NameAttribute(NameOID.SERIAL_NUMBER, f"CUIT {cuit}"))
    nombre = x509.Name(atributos)
    ahora = desde or dt.datetime.now(dt.UTC)
    certificado = (
        x509.CertificateBuilder()
        .subject_name(nombre)
        .issuer_name(nombre)
        .public_key(clave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(ahora - dt.timedelta(days=1))
        .not_valid_after(ahora + dt.timedelta(days=vence_en_dias))
        .sign(clave, hashes.SHA256())
    )
    return certificado.public_bytes(serialization.Encoding.PEM), clave


def bundle(**kwargs: object) -> bytes:
    """Lo que el Administrador sube: certificado y clave concatenados en un PEM."""
    pem, clave = certificado_y_clave(**kwargs)  # type: ignore[arg-type]
    return pem + _pem_de_la_clave(clave)


def bundle_con_clave_ajena() -> bytes:
    """Un certificado y una clave que no le corresponde. Error clásico al armar el par."""
    pem, _ = certificado_y_clave()
    return pem + _pem_de_la_clave(_clave())
