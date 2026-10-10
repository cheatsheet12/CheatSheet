"""Recording what a person accepts when an account is born (HU-E1-03, HU-E1-08).

Both ways of creating an account carry a consent: signing up (the company's terms **and** the
person's privacy policy) and accepting an invitation (the privacy policy only, because the
terms were accepted by the company's Administrator, HU-E1-08 RN-04). This service is the one
place that checks the consent against the versions in force and writes the evidence, so the
three use cases cannot drift apart.

**The backend decides, not the form** (HU-E1-03 RN-02). A missing version is rejected as an
input error; a version that is not the one in force is a conflict, because the person read a
text that has since been replaced and must read the new one before accepting it.

The checks run **before** anything is written. Everything below runs in the caller's
transaction, so a rejection also leaves no company, no user and no acceptance behind.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from cheatsheet.contexts.identity.application.errors import (
    ConsentimientoRequerido,
    VersionLegalDesactualizada,
)
from cheatsheet.contexts.identity.application.legal import vigente_a
from cheatsheet.contexts.identity.application.ports import (
    PortCatalogoLegal,
    PortRepositorioAceptacionLegal,
)
from cheatsheet.contexts.identity.domain.legal import AceptacionLegal, DocumentoLegal
from cheatsheet.contexts.identity.domain.usuario import Usuario
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId
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
        await self._registrar(
            usuario, DocumentoLegal.TERMINOS, consentimiento.version_terminos, ahora, direccion_ip
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
        await self._registrar(usuario, DocumentoLegal.PRIVACIDAD, version, ahora, direccion_ip)

    async def _registrar(
        self,
        usuario: Usuario,
        documento: DocumentoLegal,
        version: str,
        ahora: datetime,
        direccion_ip: str | None,
    ) -> None:
        empresa_id: EmpresaId = usuario.empresa_id
        await self._aceptaciones.agregar(
            AceptacionLegal.registrar(
                empresa_id=empresa_id,
                usuario_id=usuario.id,
                documento=documento,
                version=version,
                fecha_aceptacion=ahora,
            )
        )
        es_de_terminos = documento is DocumentoLegal.TERMINOS
        entidad = f"Empresa:{empresa_id}" if es_de_terminos else f"Usuario:{usuario.id}"
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
                usuario_id=usuario.id,
                direccion_ip=direccion_ip,
                detalle={"documento": documento.value, "version": version},
            )
        )
