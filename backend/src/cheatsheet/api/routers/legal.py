"""The legal documents: readable without a session, and accepted from inside one.

HU-E1-03 RN-04/05 and HU-E1-08 RN-06 (the public texts); HU-E1-03 RN-03 and HU-E1-08 RN-05
(a person who owes a new version reads what is pending and accepts it).

Own file, apart from `auth.py` (already past the 400-line limit): a public route is the
kind of thing that must be easy to find. Every public route here is listed **by exact path**
in `RUTAS_PUBLICAS`; `/legal/` is not a public prefix, so a route added here later asks for a
session unless someone deliberately lists it. The two session routes (`/legal/pendientes`,
`POST /legal/aceptaciones`) are the ones a person with a pending document may still call
(`RUTAS_CON_PENDIENTES` in the middleware).

The catalogue is built once, when the router is: the texts are files in the package and a
request never reads the disk. A text that no longer matches its published hash makes the
application refuse to start (`TextoLegalAlterado`).
"""

from __future__ import annotations

from datetime import date

from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.api.middleware.empresa import ATRIBUTO_PENDIENTES
from cheatsheet.contexts.identity.application.aceptaciones import (
    AceptarDocumentosLegales,
    Consentimiento,
    DocumentoAceptado,
)
from cheatsheet.contexts.identity.application.legal import (
    ConsultarDocumentoVigente,
    ConsultarVersionesVigentes,
    DocumentoPublicado,
)
from cheatsheet.contexts.identity.domain.legal import DocumentoLegal, VersionDeDocumento
from cheatsheet.contexts.identity.domain.valores import RolUsuario
from cheatsheet.contexts.identity.infrastructure.ensamblado import Identidad
from cheatsheet.contexts.identity.infrastructure.legal.catalogo import catalogo_publicado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel


class DocumentoSalida(BaseModel):
    documento: str
    version: str
    vigente_desde: date
    borrador: bool
    texto: str

    @classmethod
    def desde(cls, publicado: DocumentoPublicado) -> DocumentoSalida:
        return cls(
            documento=publicado.documento.value,
            version=publicado.version,
            vigente_desde=publicado.vigente_desde,
            borrador=publicado.borrador,
            texto=publicado.texto,
        )


class VersionSalida(BaseModel):
    version: str
    vigente_desde: date
    borrador: bool

    @classmethod
    def desde(cls, version: VersionDeDocumento) -> VersionSalida:
        return cls(
            version=version.version,
            vigente_desde=version.vigente_desde,
            borrador=version.borrador,
        )


class VigentesSalida(BaseModel):
    terminos: VersionSalida
    privacidad: VersionSalida


class ConsentimientoEntrada(BaseModel):
    """What the two unticked-by-default boxes send back (HU-E1-08 RN-03).

    Each field is the version the person was shown, or absent when the box was not ticked.
    The backend decides what absent or stale means; the form only transports it.
    """

    version_terminos: str | None = None
    version_privacidad: str | None = None


class PendienteSalida(BaseModel):
    """A document the person owes, with the version they will accept."""

    documento: str
    version: str
    vigente_desde: date
    borrador: bool


class PendientesSalida(BaseModel):
    pendientes: list[PendienteSalida]


class DocumentoAceptadoEntrada(BaseModel):
    documento: DocumentoLegal
    version: str


class AceptacionesEntrada(BaseModel):
    """`{documentos: [{documento, version}]}`: what the re-acceptance screen sends back."""

    documentos: list[DocumentoAceptadoEntrada]


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def consentimiento_de(entrada: ConsentimientoEntrada | None) -> Consentimiento | None:
    if entrada is None:
        return None
    return Consentimiento(
        version_terminos=entrada.version_terminos, version_privacidad=entrada.version_privacidad
    )


def crear_router(recursos: Recursos) -> APIRouter:
    """Build the legal router bound to the process resources."""
    router = APIRouter(prefix="/legal", tags=["legal"])
    catalogo = catalogo_publicado()
    documento_vigente = ConsultarDocumentoVigente(catalogo=catalogo, reloj=recursos.reloj)
    versiones_vigentes = ConsultarVersionesVigentes(catalogo=catalogo, reloj=recursos.reloj)

    @router.get("/terminos", response_model=DocumentoSalida)
    async def terminos() -> DocumentoSalida:
        return DocumentoSalida.desde(await documento_vigente.ejecutar(DocumentoLegal.TERMINOS))

    @router.get("/privacidad", response_model=DocumentoSalida)
    async def privacidad() -> DocumentoSalida:
        return DocumentoSalida.desde(await documento_vigente.ejecutar(DocumentoLegal.PRIVACIDAD))

    @router.get("/vigentes", response_model=VigentesSalida)
    async def vigentes() -> VigentesSalida:
        actuales = await versiones_vigentes.ejecutar()
        return VigentesSalida(
            terminos=VersionSalida.desde(actuales.terminos),
            privacidad=VersionSalida.desde(actuales.privacidad),
        )

    @router.get("/pendientes", response_model=PendientesSalida)
    async def pendientes(request: Request) -> PendientesSalida:
        """What this person must accept before anything else. Read from the session check."""
        debidos: frozenset[DocumentoLegal] = getattr(request.state, ATRIBUTO_PENDIENTES)
        actuales = await versiones_vigentes.ejecutar()
        por_documento = {
            DocumentoLegal.TERMINOS: actuales.terminos,
            DocumentoLegal.PRIVACIDAD: actuales.privacidad,
        }
        return PendientesSalida(
            pendientes=[
                PendienteSalida(
                    documento=documento.value,
                    version=por_documento[documento].version,
                    vigente_desde=por_documento[documento].vigente_desde,
                    borrador=por_documento[documento].borrador,
                )
                for documento in sorted(debidos, key=lambda d: d.value)
            ]
        )

    @router.post("/aceptaciones", status_code=status.HTTP_204_NO_CONTENT)
    async def aceptar(entrada: AceptacionesEntrada, request: Request) -> Response:
        empresa_id: EmpresaId = request.state.empresa_id
        usuario_id: UsuarioId = request.state.usuario_id
        # An error raised inside the body discards the transaction: nothing is half-recorded.
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Identidad.armar(unidad, recursos.settings)
            await AceptarDocumentosLegales(
                empresas=piezas.empresas,
                aceptaciones=piezas.aceptaciones,
                registrador=piezas.registrador,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=RolUsuario(request.state.rol),
                documentos=[DocumentoAceptado(d.documento, d.version) for d in entrada.documentos],
                ahora=unidad.reloj.ahora(),
                direccion_ip=_ip(request),
            )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
