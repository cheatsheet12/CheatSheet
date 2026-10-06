"""Step 2 of the onboarding and the re-acceptance of terms (HU-E1-02, HU-E1-03)."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from cheatsheet.contexts.identity.application.autorizacion import exigir_administrador
from cheatsheet.contexts.identity.application.errors import (
    CuitInexistenteEnPadron,
    CuitYaRegistrado,
)
from cheatsheet.contexts.identity.application.ports import (
    PadronNoDisponible,
    PortPadron,
    PortRepositorioEmpresa,
)
from cheatsheet.contexts.identity.domain.empresa import Empresa
from cheatsheet.contexts.identity.domain.valores import CUIT, CondicionIVA, Email, RolUsuario
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import InvarianteViolada
from cheatsheet.shared.events import PublicadorDeEventos


class CompletarDatosDeEmpresa:
    """HU-E1-02. The step that turns a registered account into an operating company.

    **`padron` is optional and usually absent at signup**, which is not a shortcut: the
    lookup needs the company's own ARCA certificate, and at step 2 there is none. Once the
    company connects ARCA, every later save goes through the registry and RN-01 starts
    biting. See `padron.py` for why that is the only place it can bite.
    """

    def __init__(
        self,
        *,
        empresas: PortRepositorioEmpresa,
        publicador: PublicadorDeEventos,
        padron: PortPadron | None = None,
    ) -> None:
        self._empresas = empresas
        self._publicador = publicador
        self._padron = padron

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        razon_social: str,
        cuit: CUIT,
        condicion_iva: CondicionIVA,
        nombre_responsable: str,
        email_contacto: Email,
        ahora: datetime,
        direccion_ip: str | None = None,
    ) -> Empresa:
        # HU-E1-02's actor is the Administrador and nobody else. The check sits here, and
        # not only in the router, for the reason `autorizacion.py` states: the rule has to
        # travel with the operation. `ConsultarPadronDeCuit` — the other half of this same
        # story — already guards itself this way; this use case did not, and an Operador
        # could rewrite the company's razon social, CUIT and condicion de IVA.
        exigir_administrador(
            rol, "Solo un Administrador puede modificar los datos fiscales de la empresa"
        )

        empresa = await self._empresas.buscar_por_id(empresa_id)
        if empresa is None:
            raise InvarianteViolada("La empresa no existe")

        # `empresa.cuit` is unique in the DER. Checking here turns a database constraint
        # violation into a message the form can show next to the field.
        cambia_el_cuit = empresa.cuit is None or empresa.cuit.valor != cuit.valor
        if cambia_el_cuit and await self._empresas.existe_cuit(cuit.valor):
            raise CuitYaRegistrado(f"El CUIT {cuit.formateado} ya esta registrado")

        await self._exigir_en_el_padron(empresa_id, cuit)

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

    async def _exigir_en_el_padron(self, empresa_id: EmpresaId, cuit: CUIT) -> None:
        """HU-E1-02 RN-01, enforced only when the registry could actually be reached.

        The three outcomes are three different things and only one of them refuses:
        the registry knows the CUIT (continue), the registry does not (refuse), or the
        registry could not be asked (continue, and say nothing — the company may simply
        not have connected ARCA yet, which is the ordinary state right after signup).
        """
        if self._padron is None:
            return
        try:
            datos = await self._padron.consultar(empresa_id=empresa_id, cuit=cuit.valor)
        except PadronNoDisponible:
            return
        if datos is None:
            raise CuitInexistenteEnPadron(
                f"ARCA no encuentra el CUIT {cuit.formateado} en su padron"
            )


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
