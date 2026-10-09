"""A stand-in for ARCA, for every environment without a real fiscal certificate.

Same guard rails as every other stand-in in this context: it validates nothing against a
real service, and **constructing it in `production` raises** — a `RuntimeError` at build
time, before the process serves a request. Here that matters more than anywhere else: a
company believing it is connected to ARCA when nothing ever reached ARCA is a company that
believes it can invoice.

**It reuses the real credential parsing and the real expiry mapping.** Only the network
call is replaced. So a certificate that is malformed, whose key does not match, or that has
already expired is rejected on a laptop exactly as it would be in production — and the
three states of the card come out of the same function either way.

The ticket it mints is fake and says so. Nothing downstream can mistake it for one that
ARCA would accept.

**The padrón answers are fabricated but travel through the real parser**, so the fiscal
translation — the one that decides which `Comprobante` epic 5 may issue — is the same
code on a laptop and in production. Two CUIT prefixes are reserved so the two awkward
outcomes can be demonstrated without a real ARCA: one that does not exist, and one that
exists but is deregistered.
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from cheatsheet.contexts.integrations.application.errors import ConexionRechazada
from cheatsheet.contexts.integrations.application.ports import (
    DatosDePadron,
    MaterialDeConexion,
    ResultadoDeConexion,
    ResultadoDeVerificacion,
    TicketEmitido,
)
from cheatsheet.contexts.integrations.domain.ticket import ServicioDeArca
from cheatsheet.contexts.integrations.domain.valores import (
    CLAVE_CUIT,
    EstadoDeConexion,
    SistemaExterno,
)
from cheatsheet.contexts.integrations.infrastructure.arca import firma
from cheatsheet.contexts.integrations.infrastructure.arca.adaptadores import (
    SERVICIO_DE_VALIDACION,
    parametros_de_la_credencial,
)
from cheatsheet.contexts.integrations.infrastructure.arca.delegacion import (
    MENSAJE_SIN_DELEGACION,
    cuit_del_material,
    formatear,
    resultado_delegado,
)
from cheatsheet.contexts.integrations.infrastructure.arca.mapeo import estado_por_vencimiento
from cheatsheet.contexts.integrations.infrastructure.arca.padron import leer_persona
from cheatsheet.platform.settings import Entorno
from cheatsheet.shared.clock import Reloj

#: WSAA tickets last twelve hours. The stand-in copies that so the renewal margin, and the
#: code that decides when to renew, are exercised with realistic numbers.
DURACION_DEL_TICKET = timedelta(hours=12)

#: Marks the payload as fabricated. If one of these ever reached ARCA it would be rejected,
#: which is the correct outcome and better than a blob that looks plausible.
PREFIJO_SIMULADO = "TICKET-SIMULADO"

#: Reserved so the blocking path of RN-01 can be demonstrated: any CUIT starting with this
#: comes back «no existe». Chosen instead of a rule over the last digit because that would
#: have made whole plausible CUITs — including the fixtures' — unusable by accident.
PREFIJO_INEXISTENTE = "20000000"

#: Reserved for a tax id that exists and is no longer in force.
PREFIJO_INACTIVO = "20999999"

#: Reserved for a company that has **not** delegated the web service to CheatSheet
#: (ADR-0014), so the rejection can be demonstrated without a real ARCA.
PREFIJO_SIN_DELEGACION = "30999999"

#: The prefixes ARCA gives to individuals. Everything else is a company, and the two get
#: different shapes of answer — which is the difference the real parser has to handle.
PREFIJOS_DE_PERSONA = ("20", "23", "24", "27")


def _rechazar_en_produccion(entorno: Entorno) -> None:
    if entorno is Entorno.PRODUCTION:
        raise RuntimeError(
            f"El adaptador simulado de {SistemaExterno.ARCA.value} no puede usarse en "
            f"produccion. Configura las credenciales reales de ARCA."
        )


class ArcaSimulado:
    """Implements the four ARCA ports at once, without a socket."""

    def __init__(self, *, entorno: Entorno, reloj: Reloj, aviso: timedelta) -> None:
        _rechazar_en_produccion(entorno)
        self._reloj = reloj
        self._aviso = aviso

    async def emitir(self, credencial: bytes, servicio: ServicioDeArca) -> TicketEmitido:
        fiscal = firma.leer_credencial(credencial)
        ahora = self._reloj.ahora()
        firma.exigir_vigente(fiscal, ahora)
        return TicketEmitido(
            servicio=servicio,
            contenido=f"{PREFIJO_SIMULADO}-{secrets.token_hex(8)}".encode(),
            expira_en=ahora + DURACION_DEL_TICKET,
        )

    async def conectar(self, material: MaterialDeConexion) -> ResultadoDeConexion:
        fiscal = firma.leer_credencial(material.contenido)
        firma.exigir_vigente(fiscal, self._reloj.ahora())
        if not material.contenido.strip():
            raise ConexionRechazada("Falta la credencial fiscal")
        ticket = await self.emitir(material.contenido, SERVICIO_DE_VALIDACION)
        return ResultadoDeConexion(
            credencial=material.contenido,
            parametros=parametros_de_la_credencial(fiscal),
            tickets=(ticket,),
        )

    async def consultar(
        self, *, ticket: bytes, parametros: Mapping[str, Any], cuit: str
    ) -> DatosDePadron | None:
        """Fabricates a `getPersona` answer and reads it back with the real parser."""
        del ticket, parametros  # the stand-in authenticates nothing
        digitos = "".join(c for c in cuit if c.isdigit())
        if digitos.startswith(PREFIJO_INEXISTENTE):
            return None
        return leer_persona(_respuesta_simulada(digitos), digitos)

    async def verificar(
        self, credencial: bytes, parametros: dict[str, Any]
    ) -> ResultadoDeVerificacion:
        del parametros
        try:
            fiscal = firma.leer_credencial(credencial)
        except ConexionRechazada as exc:
            # Same answer the real adapter gives, for the same reason: a stored credential
            # that no longer parses is a data problem, and it belongs on the card.
            return ResultadoDeVerificacion(
                EstadoDeConexion.ATENCION, f"No se pudo leer la credencial guardada: {exc}"
            )
        estado, detalle = estado_por_vencimiento(fiscal.vence_en, self._reloj.ahora(), self._aviso)
        return ResultadoDeVerificacion(estado, detalle, parametros_de_la_credencial(fiscal))


class ArcaSimuladoPorDelegacion(ArcaSimulado):
    """The stand-in under ADR-0014: companies delegate, the platform holds the certificate.

    Connecting reads the company's CUIT and answers as ARCA would about its delegation; a
    CUIT starting with `PREFIJO_SIN_DELEGACION` has not delegated. There is no platform
    certificate in a simulated deployment, so minting a ticket reads no credential.
    """

    async def emitir(self, credencial: bytes, servicio: ServicioDeArca) -> TicketEmitido:
        del credencial  # no platform certificate exists in a simulated deployment
        return TicketEmitido(
            servicio=servicio,
            contenido=f"{PREFIJO_SIMULADO}-{secrets.token_hex(8)}\n{PREFIJO_SIMULADO}".encode(),
            expira_en=self._reloj.ahora() + DURACION_DEL_TICKET,
        )

    async def conectar(self, material: MaterialDeConexion) -> ResultadoDeConexion:
        cuit = cuit_del_material(material)
        if cuit.startswith(PREFIJO_SIN_DELEGACION):
            raise ConexionRechazada(MENSAJE_SIN_DELEGACION.format(cuit=formatear(cuit)))
        return resultado_delegado(cuit)

    async def verificar(
        self, credencial: bytes, parametros: dict[str, Any]
    ) -> ResultadoDeVerificacion:
        del credencial
        cuit = "".join(c for c in str(parametros.get(CLAVE_CUIT, "")) if c.isdigit())
        if not cuit or cuit.startswith(PREFIJO_SIN_DELEGACION):
            return ResultadoDeVerificacion(
                EstadoDeConexion.NO_CONECTADO, MENSAJE_SIN_DELEGACION.format(cuit=cuit)
            )
        return ResultadoDeVerificacion(
            EstadoDeConexion.CONECTADO, None, resultado_delegado(cuit).parametros
        )


def _respuesta_simulada(cuit: str) -> str:
    """A `getPersona` body with the shape ARCA returns, filled with obvious fiction.

    An individual comes back as a monotributista with `apellido` and `nombre`; a company
    as a responsable inscripto with `razonSocial` and its list of taxes. Between them they
    cover both branches of `leer_persona`, so the stand-in exercises the parser instead of
    walking around it.
    """
    estado = "INACTIVO" if cuit.startswith(PREFIJO_INACTIVO) else "ACTIVO"
    if cuit[:2] in PREFIJOS_DE_PERSONA:
        identidad = (
            "<apellido>SIMULADO</apellido><nombre>CONTRIBUYENTE</nombre>"
            "<tipoPersona>FISICA</tipoPersona>"
        )
        regimen = (
            "<datosMonotributo><categoriaMonotributo>C</categoriaMonotributo></datosMonotributo>"
        )
    else:
        identidad = (
            f"<razonSocial>EMPRESA SIMULADA {cuit}</razonSocial><tipoPersona>JURIDICA</tipoPersona>"
        )
        regimen = (
            "<datosRegimenGeneral><impuesto><idImpuesto>30</idImpuesto>"
            "<descripcionImpuesto>IVA</descripcionImpuesto></impuesto></datosRegimenGeneral>"
        )
    return (
        "<personaReturn>"
        f"<datosGenerales><idPersona>{cuit}</idPersona>"
        f"<estadoClave>{estado}</estadoClave>{identidad}</datosGenerales>"
        f"{regimen}"
        "</personaReturn>"
    )
