"""The debt of HU-E1-02 RN-01, paid where it can actually be paid.

The story asks for the CUIT to be validated against ARCA «en tiempo real» at step 2 of the
onboarding. It cannot be: the lookup needs an access ticket, the ticket needs the company's
own certificate, and the certificate is loaded afterwards, in Configuración → Integraciones.
The alternative — a platform-wide ARCA credential — was ruled out by decision D1 and the
previous unit deleted the variables that would have held one.

So RN-01 is honoured over the life of the company rather than in the instant of signup:

- `ConsultarPadronDeCuit` is the lookup behind the «Validar contra ARCA» button;
- `RevalidarDatosFiscales` runs the moment ARCA is connected, which is the first instant
  the lookup is possible at all;
- `CompletarDatosDeEmpresa` (in `onboarding.py`) refuses a CUIT the registry does not know.

**The distinction that governs all three**: not-found blocks, could-not-ask does not. They
arrive as different things — `None` and `PadronNoDisponible` — and are never merged, so a
bad afternoon at ARCA cannot lock a company out of its own fiscal data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from cheatsheet.contexts.identity.application.autorizacion import exigir_administrador
from cheatsheet.contexts.identity.application.ports import (
    DatosFiscalesDePadron,
    PadronNoDisponible,
    PortPadron,
    PortRepositorioEmpresa,
)
from cheatsheet.contexts.identity.domain.empresa import Empresa
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import InvarianteViolada
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.fiscal import CUIT
from cheatsheet.shared.roles import RolUsuario

#: What the audit log records when a check fails. Two actions rather than one action
#: with a detail, because `EventoAuditable` has no free-text field — and inventing one
#: would mean a column on the shared audit table, which this unit deliberately does not
#: add. Two named actions are also what epic 10 can filter on.
ACCION_CUIT_INEXISTENTE = "padron_cuit_inexistente"
ACCION_CERTIFICADO_AJENO = "padron_certificado_ajeno"


class EstadoDeConsulta(StrEnum):
    """The three answers the screen has to tell apart, and it must show three messages."""

    ENCONTRADO = "ENCONTRADO"
    NO_ENCONTRADO = "NO_ENCONTRADO"
    NO_DISPONIBLE = "NO_DISPONIBLE"


@dataclass(frozen=True, slots=True)
class VistaDePadron:
    """What the form receives after asking about a CUIT."""

    estado: EstadoDeConsulta
    datos: DatosFiscalesDePadron | None = None
    #: Why it could not be asked, in words the Administrator can act on. Never a stack
    #: trace and never the provider's raw fault: those go to the log.
    motivo: str | None = None


class ConsultarPadronDeCuit:
    """The lookup behind «Validar contra ARCA». Writes nothing."""

    def __init__(self, *, padron: PortPadron) -> None:
        self._padron = padron

    async def ejecutar(self, *, empresa_id: EmpresaId, cuit: str, rol: RolUsuario) -> VistaDePadron:
        """Administrador only: HU-E1-02's actor, and each call spends a request at ARCA."""
        exigir_administrador(rol)
        # Format and check digit first (HU-E1-02: an invalid CUIT «no consulta a ARCA»). The
        # panel already checks, but this is the API, and each lookup spends a request at ARCA.
        valido = CUIT(cuit).valor
        try:
            datos = await self._padron.consultar(empresa_id=empresa_id, cuit=valido)
        except PadronNoDisponible as exc:
            return VistaDePadron(EstadoDeConsulta.NO_DISPONIBLE, motivo=str(exc))
        if datos is None:
            return VistaDePadron(EstadoDeConsulta.NO_ENCONTRADO)
        return VistaDePadron(EstadoDeConsulta.ENCONTRADO, datos=datos)


@dataclass(frozen=True, slots=True)
class AvisoFiscal:
    """Something about the company's fiscal data that does not add up.

    Returned rather than stored. There is no column for it because there is no state to
    keep: the next lookup recomputes it, and the audit log already holds the history. A
    boolean on `Empresa` would be a second place for a truth that lives at ARCA.
    """

    motivo: str


class RevalidarDatosFiscales:
    """Runs when ARCA is connected — the first moment the registry can be asked at all.

    Two questions, and the second one is nearly free:

    1. **Does the registry know this CUIT?** If it does, whatever the company left blank
       gets filled in — the autocomplete HU-E1-02's first acceptance criterion asks for,
       arriving late but arriving.
    2. **Does the certificate belong to this company?** ARCA puts the CUIT in the
       certificate's subject and `conexion-arca` already extracted it. A mismatch means
       somebody loaded another taxpayer's certificate, and without this check it surfaces
       when the first document is issued in the wrong name.

    **What it never does is overwrite.** A razón social already entered stays as entered,
    even when ARCA says something else: nobody is watching this run, and silently
    rewriting a company's own name on the strength of an unattended lookup is not a
    correction, it is a surprise. The difference is reported instead.
    """

    def __init__(
        self,
        *,
        empresas: PortRepositorioEmpresa,
        padron: PortPadron,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._empresas = empresas
        self._padron = padron
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        ahora: datetime,
        cuit_declarado: str | None = None,
        usuario_id: UsuarioId | None = None,
        direccion_ip: str | None = None,
    ) -> AvisoFiscal | None:
        empresa = await self._empresas.buscar_por_id(empresa_id)
        if empresa is None:
            raise InvarianteViolada("La empresa no existe")
        if empresa.cuit is None:
            # Nothing to check against yet. Reachable in theory — connecting ARCA needs a
            # session, and a session with no fiscal data means the onboarding is unfinished.
            return None

        desajuste = _desajuste_de_certificado(empresa.cuit.valor, cuit_declarado)
        if desajuste is not None:
            await self._auditar(
                empresa_id, ACCION_CERTIFICADO_AJENO, ahora, usuario_id, direccion_ip
            )
            return AvisoFiscal(desajuste)

        try:
            datos = await self._padron.consultar(empresa_id=empresa_id, cuit=empresa.cuit.valor)
        except PadronNoDisponible:
            # Silent on purpose: the certificate was just accepted and this is a courtesy
            # check. Turning an unreachable registry into a warning on that screen would
            # teach the Administrator to ignore the warning that matters.
            return None

        if datos is None:
            motivo = (
                f"ARCA no encuentra el CUIT {empresa.cuit.formateado} en su padron. "
                f"Revisa los datos fiscales de la empresa"
            )
            await self._auditar(
                empresa_id, ACCION_CUIT_INEXISTENTE, ahora, usuario_id, direccion_ip
            )
            return AvisoFiscal(motivo)

        completados = _completar_vacios(empresa, datos)
        if completados:
            await self._empresas.guardar(empresa)
        if not datos.activo:
            return AvisoFiscal(
                f"ARCA informa que el CUIT {empresa.cuit.formateado} no esta activo en su padron"
            )
        return _diferencia(empresa, datos)

    async def _auditar(
        self,
        empresa_id: EmpresaId,
        accion: str,
        ahora: datetime,
        usuario_id: UsuarioId | None,
        direccion_ip: str | None,
    ) -> None:
        """The finding goes to the Log de Operaciones, never the registry's contents.

        What ARCA answered is somebody's real name and tax situation. The log records
        that the check ran and what it concluded, which is what epic 10 needs to show.
        """
        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                modulo=Modulo.IDENTITY,
                accion=accion,
                entidad_afectada=f"Empresa:{empresa_id}",
                # `Resultado` has two members and this is the one that means «no salió
                # bien». The check ran; what it found is a problem with the company's
                # fiscal data, and the action name says which of the two it was.
                resultado=Resultado.ERROR,
                usuario_id=usuario_id,
                direccion_ip=direccion_ip,
            )
        )


def _desajuste_de_certificado(cuit_empresa: str, cuit_declarado: str | None) -> str | None:
    """`None` when they match, or when the certificate does not say.

    A certificate with no CUIT in its subject is unusual but usable — `conexion-arca`
    never blocked a connection on it — so it cannot be treated as a mismatch here either.
    """
    if not cuit_declarado:
        return None
    if _digitos(cuit_declarado) == _digitos(cuit_empresa):
        return None
    return (
        "El certificado cargado en ARCA pertenece a otro CUIT que el de la empresa. "
        "Verifica que sea el certificado correcto antes de emitir comprobantes"
    )


def _completar_vacios(empresa: Empresa, datos: DatosFiscalesDePadron) -> bool:
    """Fill only what is empty. Returns whether anything changed."""
    cambio = False
    if empresa.razon_social is None and datos.razon_social:
        empresa.razon_social = datos.razon_social
        cambio = True
    if empresa.condicion_iva is None and datos.condicion_iva is not None:
        empresa.condicion_iva = datos.condicion_iva
        cambio = True
    return cambio


def _diferencia(empresa: Empresa, datos: DatosFiscalesDePadron) -> AvisoFiscal | None:
    """Report what disagrees, having changed nothing."""
    if datos.condicion_iva is not None and empresa.condicion_iva is not datos.condicion_iva:
        return AvisoFiscal(
            f"ARCA registra la empresa como {datos.condicion_iva.value.replace('_', ' ').lower()}, "
            f"y en CheatSheet figura como "
            f"{str(empresa.condicion_iva or '').replace('_', ' ').lower()}"
        )
    return None


def _digitos(valor: str) -> str:
    return "".join(caracter for caracter in valor if caracter.isdigit())
