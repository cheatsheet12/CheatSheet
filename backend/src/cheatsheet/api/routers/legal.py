"""The legal documents, readable without a session (HU-E1-03 RN-04/05, HU-E1-08 RN-06).

Own file, apart from `auth.py` (already past the 400-line limit): a public route is the
kind of thing that must be easy to find. Every route here is listed **by exact path** in
`RUTAS_PUBLICAS`; `/legal/` is not a public prefix, so a route added here later asks for a
session unless someone deliberately lists it.

The catalogue is built once, when the router is: the texts are files in the package and a
request never reads the disk. A text that no longer matches its published hash makes the
application refuse to start (`TextoLegalAlterado`).
"""

from __future__ import annotations

from datetime import date

from cheatsheet.api.dependencies import Recursos
from cheatsheet.contexts.identity.application.legal import (
    ConsultarDocumentoVigente,
    ConsultarVersionesVigentes,
    DocumentoPublicado,
)
from cheatsheet.contexts.identity.domain.legal import DocumentoLegal, VersionDeDocumento
from cheatsheet.contexts.identity.infrastructure.legal.catalogo import CatalogoLegalEnArchivos
from fastapi import APIRouter
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


def crear_router(recursos: Recursos) -> APIRouter:
    """Build the legal router bound to the process resources."""
    router = APIRouter(prefix="/legal", tags=["legal"])
    catalogo = CatalogoLegalEnArchivos()
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

    return router
