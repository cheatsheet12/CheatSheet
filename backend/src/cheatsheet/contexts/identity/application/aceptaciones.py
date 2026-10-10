"""Recording what a person accepts, at sign-up and afterwards (HU-E1-03, HU-E1-08).

Both ways of creating an account carry a consent: signing up (the company's terms **and** the
person's privacy policy) and accepting an invitation (the privacy policy only, because the
terms were accepted by the company's Administrator, HU-E1-08 RN-04). This service is the one
place that checks the consent against the versions in force and writes the evidence, so the
three use cases cannot drift apart. A person who is already inside a session and owes a new
version (HU-E1-03 RN-03, HU-E1-08 RN-05) accepts through `AceptarDocumentosLegales`, which
goes through the same service.

**The backend decides, not the form** (HU-E1-03 RN-02). A missing version is rejected as an
input error; a version that is not the one in force is a conflict, because the person read a
text that has since been replaced and must read the new one before accepting it.

The checks run **before** anything is written. Everything below runs in the caller's
transaction, so a rejection also leaves no company, no user and no acceptance behind.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from cheatsheet.contexts.identity.application.autorizacion import exigir_administrador
from cheatsheet.contexts.identity.application.errors import (
    ConsentimientoRequerido,
    VersionLegalDesactualizada,
)
from cheatsheet.contexts.identity.application.legal import vigente_a
from cheatsheet.contexts.identity.application.ports import (
    PortCatalogoLegal,
    PortRepositorioAceptacionLegal,
    PortRepositorioEmpresa,
)
from cheatsheet.contexts.identity.domain.legal import AceptacionLegal, DocumentoLegal
from cheatsheet.contexts.identity.domain.usuario import Usuario
from cheatsheet.contexts.identity.domain.valores import RolUsuario
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada
from cheatsheet.shared.events import PublicadorDeEventos

MENSAJE_DE_TERMINOS = "Debe aceptar los términos y condiciones para continuar."
MENSAJE_DE_PRIVACIDAD = "Debe aceptar la política de privacidad para continuar."


@dataclass(frozen=True, slots=True)
class Consentimiento:
    """The versions the person says they accepted. `None` is an unticked box."""

    version_terminos: str | None
    version_privacidad: str | None


@dataclass(frozen=True, slots=True)
class ConsentimientoVigente:
    """A consent already checked against the versions in force."""

    version_terminos: str
    version_privacidad: str


class RegistradorDeAceptaciones:
    """Checks a consent against the catalogue and records it."""

    def __init__(
        self,
        *,
        catalogo: PortCatalogoLegal,
        aceptaciones: PortRepositorioAceptacionLegal,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._catalogo = catalogo
        self._aceptaciones = aceptaciones
        self._publicador = publicador

    def exigir_consentimiento(
        self, consentimiento: Consentimiento | None, ahora: datetime
    ) -> ConsentimientoVigente:
        """Both boxes, both in force. Terms are checked first, as the form lists them."""
        dado = consentimiento or Consentimiento(None, None)
        terminos = self._exigir(DocumentoLegal.TERMINOS, dado.version_terminos, ahora)
        privacidad = self._exigir(DocumentoLegal.PRIVACIDAD, dado.version_privacidad, ahora)
        return ConsentimientoVigente(version_terminos=terminos, version_privacidad=privacidad)

    def exigir_privacidad(self, version_privacidad: str | None, ahora: datetime) -> str:
        """The invitee's single box (HU-E1-08 RN-04)."""
        return self._exigir(DocumentoLegal.PRIVACIDAD, version_privacidad, ahora)

    def exigir_vigente(self, documento: DocumentoLegal, version: str, ahora: datetime) -> str:
        """One document, in force today: what a person already inside accepts."""
        return self._exigir(documento, version, ahora)

    def _exigir(self, documento: DocumentoLegal, version: str | None, ahora: datetime) -> str:
        if not version:
            raise ConsentimientoRequerido(
                MENSAJE_DE_TERMINOS
                if documento is DocumentoLegal.TERMINOS
                else MENSAJE_DE_PRIVACIDAD
            )
        if vigente_a(self._catalogo, ahora, documento).version != version:
            raise VersionLegalDesactualizada(
                f"La version {version} de {documento.value} ya no es la vigente"
            )
        return version

    async def registrar_alta(
        self,
        *,
        usuario: Usuario,
        consentimiento: ConsentimientoVigente,
        ahora: datetime,
        direccion_ip: str | None,
    ) -> None:
        """Terms (the company's, through its first Administrator) and privacy (the person's)."""
        await self.registrar(
            empresa_id=usuario.empresa_id,
            usuario_id=usuario.id,
            documento=DocumentoLegal.TERMINOS,
            version=consentimiento.version_terminos,
            ahora=ahora,
            direccion_ip=direccion_ip,
        )
        await self.registrar_privacidad(
            usuario=usuario,
            version=consentimiento.version_privacidad,
            ahora=ahora,
            direccion_ip=direccion_ip,
        )

    async def registrar_privacidad(
        self, *, usuario: Usuario, version: str, ahora: datetime, direccion_ip: str | None
    ) -> None:
        await self.registrar(
            empresa_id=usuario.empresa_id,
            usuario_id=usuario.id,
            documento=DocumentoLegal.PRIVACIDAD,
            version=version,
            ahora=ahora,
            direccion_ip=direccion_ip,
        )

    async def registrar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        documento: DocumentoLegal,
        version: str,
        ahora: datetime,
        direccion_ip: str | None,
    ) -> None:
        """Writes the evidence and the audit event, unless the table already had that row.

        Two requests racing to record the same acceptance leave one row (the table refuses the
        second) and so one event: the log must not say twice what happened once.
        """
        registrada = await self._aceptaciones.agregar(
            AceptacionLegal.registrar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                documento=documento,
                version=version,
                fecha_aceptacion=ahora,
            )
        )
        if not registrada:
            return
        es_de_terminos = documento is DocumentoLegal.TERMINOS
        entidad = f"Empresa:{empresa_id}" if es_de_terminos else f"Usuario:{usuario_id}"
        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                modulo=Modulo.IDENTITY,
                accion="aceptar_terminos" if es_de_terminos else "aceptar_politica_de_privacidad",
                # The version is in the entity too, so the audit list shows which text was
                # accepted without opening each event (HU-E1-08 criterion 8).
                entidad_afectada=f"{entidad} {documento.value.lower()} {version}",
                resultado=Resultado.COMPLETADO,
                usuario_id=usuario_id,
                direccion_ip=direccion_ip,
                detalle={"documento": documento.value, "version": version},
            )
        )


@dataclass(frozen=True, slots=True)
class DocumentoAceptado:
    """One `(document, version)` pair a person says they accept."""

    documento: DocumentoLegal
    version: str


class AceptarDocumentosLegales:
    """A person already inside accepts the versions now in force (HU-E1-03 RN-03, HU-E1-08 RN-05).

    Guarantees:

    - **only what is in force today** can be accepted (`VersionLegalDesactualizada`, 409);
    - **the terms belong to the company, so only an Administrador accepts them**
      (`PermisoDenegado`, 403); a privacy policy is personal and any role accepts its own;
    - **all or nothing**: every document is validated before the first is written, so a request
      that mixes a valid privacy policy with terms the role may not accept records neither;
    - **idempotent per version**: accepting what is already on record writes no second row and
      no second event, whether the repeat is a double click or a retry;
    - the terms on record in `empresa.terminos_*` (the DER's state in force) move with the
      acceptance, in the same transaction as the evidence row.
    """

    def __init__(
        self,
        *,
        empresas: PortRepositorioEmpresa,
        aceptaciones: PortRepositorioAceptacionLegal,
        registrador: RegistradorDeAceptaciones,
    ) -> None:
        self._empresas = empresas
        self._aceptaciones = aceptaciones
        self._registrador = registrador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        documentos: Sequence[DocumentoAceptado],
        ahora: datetime,
        direccion_ip: str | None = None,
    ) -> None:
        if not documentos:
            raise EntradaInvalida("Indique al menos un documento legal para aceptar")
        for aceptado in documentos:
            if aceptado.documento is DocumentoLegal.TERMINOS:
                exigir_administrador(
                    rol, "Solo un Administrador puede aceptar los términos de la empresa"
                )
            self._registrador.exigir_vigente(aceptado.documento, aceptado.version, ahora)
        for aceptado in dict.fromkeys(documentos):
            if aceptado.documento is DocumentoLegal.TERMINOS:
                await self._terminos(empresa_id, usuario_id, aceptado.version, ahora, direccion_ip)
            else:
                await self._privacidad(
                    empresa_id, usuario_id, aceptado.version, ahora, direccion_ip
                )

    async def _privacidad(
        self,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        version: str,
        ahora: datetime,
        direccion_ip: str | None,
    ) -> None:
        if await self._aceptaciones.acepto(usuario_id, DocumentoLegal.PRIVACIDAD, version):
            return
        await self._registrador.registrar(
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            documento=DocumentoLegal.PRIVACIDAD,
            version=version,
            ahora=ahora,
            direccion_ip=direccion_ip,
        )

    async def _terminos(
        self,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        version: str,
        ahora: datetime,
        direccion_ip: str | None,
    ) -> None:
        empresa = await self._empresas.buscar_por_id(empresa_id)
        if empresa is None:
            raise InvarianteViolada("La empresa no existe")
        # The terms are the company's: if another Administrador already accepted this version,
        # there is nothing left to record.
        if not empresa.debe_reaceptar_terminos(version):
            return
        empresa.aceptar_terminos(version, ahora)
        await self._empresas.guardar(empresa)
        await self._registrador.registrar(
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            documento=DocumentoLegal.TERMINOS,
            version=version,
            ahora=ahora,
            direccion_ip=direccion_ip,
        )
