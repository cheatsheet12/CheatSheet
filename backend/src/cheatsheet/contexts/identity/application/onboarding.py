"""Step 2 of the onboarding and the re-acceptance of terms (HU-E1-02, HU-E1-03)."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from cheatsheet.contexts.identity.application.errors import CuitYaRegistrado
from cheatsheet.contexts.identity.application.ports import PortRepositorioEmpresa
from cheatsheet.contexts.identity.domain.empresa import Empresa
from cheatsheet.contexts.identity.domain.valores import CUIT, CondicionIVA, Email
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import InvarianteViolada
from cheatsheet.shared.events import PublicadorDeEventos


class CompletarDatosDeEmpresa:
    """HU-E1-02. The step that turns a registered account into an operating company."""

    def __init__(
        self, *, empresas: PortRepositorioEmpresa, publicador: PublicadorDeEventos
    ) -> None:
        self._empresas = empresas
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        razon_social: str,
        cuit: CUIT,
        condicion_iva: CondicionIVA,
        nombre_responsable: str,
        email_contacto: Email,
        ahora: datetime,
        direccion_ip: str | None = None,
    ) -> Empresa:
        empresa = await self._empresas.buscar_por_id(empresa_id)
        if empresa is None:
            raise InvarianteViolada("La empresa no existe")

        # `empresa.cuit` is unique in the DER. Checking here turns a database constraint
        # violation into a message the form can show next to the field.
        cambia_el_cuit = empresa.cuit is None or empresa.cuit.valor != cuit.valor
        if cambia_el_cuit and await self._empresas.existe_cuit(cuit.valor):
            raise CuitYaRegistrado(f"El CUIT {cuit.formateado} ya esta registrado")

        empresa.completar_datos_fiscales(
            razon_social=razon_social,
            cuit=cuit,
            condicion_iva=condicion_iva,
            nombre_responsable=nombre_responsable,
            email_contacto=email_contacto,
        )
        await self._empresas.guardar(empresa)
        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                modulo=Modulo.IDENTITY,
                accion="completar_datos_de_empresa",
                entidad_afectada=f"Empresa:{empresa_id}",
                resultado=Resultado.COMPLETADO,
                usuario_id=usuario_id,
                direccion_ip=direccion_ip,
            )
        )
        return empresa


class AceptarTerminos:
    """HU-E1-03 RN-03: a new version is accepted on the next sign-in."""

    def __init__(
        self, *, empresas: PortRepositorioEmpresa, publicador: PublicadorDeEventos
    ) -> None:
        self._empresas = empresas
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        version: str,
        ahora: datetime,
        direccion_ip: str | None = None,
    ) -> Empresa:
        empresa = await self._empresas.buscar_por_id(empresa_id)
        if empresa is None:
            raise InvarianteViolada("La empresa no existe")

        empresa.aceptar_terminos(version, ahora)
        await self._empresas.guardar(empresa)
        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                modulo=Modulo.IDENTITY,
                accion="aceptar_terminos",
                entidad_afectada=f"Empresa:{empresa_id}",
                resultado=Resultado.COMPLETADO,
                usuario_id=usuario_id,
                direccion_ip=direccion_ip,
                # The version is the whole point of the record, so it is in the log too:
                # the audit panel must answer "which text did they accept" without a join.
            )
        )
        return empresa
