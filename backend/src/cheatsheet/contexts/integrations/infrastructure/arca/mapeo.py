"""ARCA's vocabulary in, ours out.

Two translations live here and they answer different questions. `interpretar_falla` decides
what a SOAP fault *means* — was the credential refused, or did ARCA have a bad minute?
`estado_por_vencimiento` decides what a certificate's expiry date means for the card.

**The catch-all matters most, again.** ARCA adds fault codes without announcing it, and an
unrecognised one raising a `KeyError` inside a daily Beat task is an integration that goes
silent. Anything unknown becomes `ATENCION` carrying the raw code, which is visible and
destroys nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from cheatsheet.contexts.integrations.application.errors import (
    ConexionRechazada,
    ProveedorNoDisponible,
)
from cheatsheet.contexts.integrations.domain.valores import EstadoDeConexion

#: Parameter keys this adapter writes onto the aggregate. Ours, not ARCA's.
CLAVE_CUIT = "cuit"
CLAVE_TITULAR = "titular"
CLAVE_VENCIMIENTO = "certificado_vence_en"

#: ARCA answers this when a live ticket already exists for the same CUIT and service.
#: **Not an error**: it is the provider confirming the credential works, and the only
#: reason it is a problem at all is if we failed to keep the ticket it gave us.
CODIGO_YA_AUTENTICADO = "coe.alreadyAuthenticated"

#: Faults that mean the credential itself was refused. Repeating the call changes nothing.
RECHAZOS: dict[str, str] = {
    "cms.sign.InvalidCertificate": "ARCA no reconoce el certificado como valido",
    "cms.cert.untrusted": "El certificado no esta habilitado para este servicio en ARCA",
    "cms.cert.expired": "El certificado esta vencido para ARCA",
    "cms.cert.notFound": "ARCA no encontro el certificado. Verifica que este asociado al CUIT",
    "cms.cert.notAuthorized": "El certificado no tiene autorizado el servicio solicitado",
    "cms.bad": "ARCA no pudo procesar la firma del pedido",
    "ns1.cms.sign.InvalidCertificate": "ARCA no reconoce el certificado como valido",
}

#: Faults that mean ARCA is having a moment. Worth retrying.
TRANSITORIOS = frozenset({"coe.notAuthorized", "cms.internalError", "soapenv:Server"})


class YaAutenticado(RuntimeError):
    """ARCA still holds a live ticket for this CUIT and service.

    Its own type because the caller's reaction is neither "reject" nor "retry": it is
    "use the one you already have". Only when we do **not** have it does this become a
    real problem, and then it is one that resolves itself when the old ticket expires.
    """


@dataclass(frozen=True, slots=True)
class FallaDeArca:
    codigo: str
    detalle: str


def interpretar_falla(falla: FallaDeArca) -> Exception:
    """Turn a SOAP fault into the exception the use case should see."""
    if falla.codigo == CODIGO_YA_AUTENTICADO:
        return YaAutenticado(falla.detalle or "ARCA ya emitio un ticket vigente")
    if falla.codigo in RECHAZOS:
        return ConexionRechazada(RECHAZOS[falla.codigo])
    if falla.codigo in TRANSITORIOS:
        return ProveedorNoDisponible(f"ARCA respondio {falla.codigo}: {falla.detalle}")
    # Unknown code. Treated as a rejection rather than as an outage on purpose: retrying
    # something we do not understand against a fiscal service is the wrong default, and
    # the raw code travels in the message so it can be looked up.
    return ConexionRechazada(f"ARCA rechazo la conexion ({falla.codigo}): {falla.detalle}")


def estado_por_vencimiento(
    vence_en: datetime, ahora: datetime, aviso: timedelta
) -> tuple[EstadoDeConexion, str | None]:
    """What the certificate's expiry date means for the card, with no network call.

    Three outcomes, and the middle one is the one that earns its keep: renewing a
    certificate at ARCA takes days, so finding out on the day it expired means not being
    able to invoice. `ATENCION` before the fact is the difference between a warning and an
    outage.
    """
    if vence_en <= ahora:
        return (
            EstadoDeConexion.NO_CONECTADO,
            f"El certificado vencio el {vence_en.date().isoformat()}",
        )
    if vence_en - ahora <= aviso:
        dias = max((vence_en - ahora).days, 1)
        return (
            EstadoDeConexion.ATENCION,
            f"El certificado vence en {dias} dias ({vence_en.date().isoformat()}). "
            f"Renovalo en ARCA antes de esa fecha",
        )
    return EstadoDeConexion.CONECTADO, None
