"""The four things a company does with its customer catalogue (HU-E4-01).

List, create, edit, and take out of circulation. **There is no delete**, and that is a
decision rather than an omission: ADR-007 says what leaves the company's spreadsheet is
marked absent and never removed, and `comprobante`, `cobro` and `turno` reference a
client by id without a declared foreign key (DER gap H4) — so nothing in the database
would stop a physical delete from leaving tax documents pointing at nothing.

`origen` is set once, at creation, and no operation here takes it as input (RN-01).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from cheatsheet.contexts.master_data.application.autorizacion import (
    exigir_escritura,
    exigir_lectura,
)
from cheatsheet.contexts.master_data.application.errors import ClienteNoEncontrado, CuitInexistente
from cheatsheet.contexts.master_data.application.padron import (
    EstadoDeConsulta,
    VistaDePadron,
    consultar_padron,
    cuit_desde,
)
from cheatsheet.contexts.master_data.application.ports import PortPadron, PortRepositorioCliente
from cheatsheet.contexts.master_data.domain.cliente import (
    Cliente,
    FiltrosDeCliente,
    ListadoDeClientes,
    Pagina,
)
from cheatsheet.contexts.master_data.domain.valores import OrigenDato
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.clock import Reloj
from cheatsheet.shared.contacto import Email, Telefono
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.fiscal import CUIT, CondicionIVA
from cheatsheet.shared.roles import RolUsuario

ACCION_REGISTRADO = "cliente_registrado"
ACCION_EDITADO = "cliente_editado"
ACCION_DESACTIVADO = "cliente_desactivado"
ACCION_REACTIVADO = "cliente_reactivado"


@dataclass(frozen=True, slots=True)
class DatosDeCliente:
    """What PAN-DM-01's form sends, still as text.

    **`nombre` is optional here and mandatory on the aggregate**, and the gap between the
    two is HU-E4-01's second acceptance criterion: creating with a valid CUIT «completa
    razón social y condición IVA». If the registry knows the tax id, its razón social is
    the name — so a form that sends only a CUIT is a legitimate request, and the aggregate
    still never exists without a name.
    """

    nombre: str | None = None
    cuit: str | None = None
    condicion_iva: CondicionIVA | None = None
    contacto_whatsapp: str | None = None
    contacto_email: str | None = None


@dataclass(frozen=True, slots=True)
class DatosFiscalesResueltos:
    """The tax id and VAT condition a save ended up with, and how ARCA answered."""

    cuit: CUIT | None
    condicion_iva: CondicionIVA | None
    razon_social: str | None
    #: `None` when there was no CUIT to ask about.
    validacion: VistaDePadron | None


@dataclass(frozen=True, slots=True)
class VistaDeCliente:
    """One client, plus what the registry said if it was consulted.

    The screen needs the second half: a client saved while ARCA was unreachable looks
    exactly like a validated one in the row, and the user has to be told the difference
    at the moment it happens.
    """

    cliente: Cliente
    validacion: VistaDePadron | None = None


async def _resolver_datos_fiscales(
    padron: PortPadron, *, empresa_id: EmpresaId, datos: DatosDeCliente
) -> DatosFiscalesResueltos:
    """Validate the CUIT structurally, then ask ARCA — and obey the answer.

    Not found blocks (`CuitInexistente`); could not ask does not. See
    `application/padron.py` for why those two are never the same thing.
    """
    if datos.cuit is None or not datos.cuit.strip():
        return DatosFiscalesResueltos(None, datos.condicion_iva, None, None)
    cuit = cuit_desde(datos.cuit)
    vista = await consultar_padron(padron, empresa_id=empresa_id, cuit=cuit)
    if vista.estado is EstadoDeConsulta.NO_ENCONTRADO:
        raise CuitInexistente(f"ARCA no conoce el CUIT {cuit.formateado}")
    if vista.estado is EstadoDeConsulta.ENCONTRADO and vista.datos is not None:
        # What the user chose wins over what the registry says. The autocomplete of the
        # acceptance criterion fills what was left blank; it does not correct anybody.
        return DatosFiscalesResueltos(
            cuit,
            datos.condicion_iva or vista.datos.condicion_iva,
            vista.datos.razon_social,
            vista,
        )
    return DatosFiscalesResueltos(cuit, datos.condicion_iva, None, vista)


def _contacto(datos: DatosDeCliente) -> tuple[Telefono | None, Email | None]:
    whatsapp = datos.contacto_whatsapp.strip() if datos.contacto_whatsapp else ""
    email = datos.contacto_email.strip() if datos.contacto_email else ""
    return (Telefono(whatsapp) if whatsapp else None, Email(email) if email else None)


async def _auditar(
    publicador: PublicadorDeEventos,
    *,
    empresa_id: EmpresaId,
    usuario_id: UsuarioId | None,
    ahora: datetime,
    accion: str,
    cliente_id: UUID,
    direccion_ip: str | None,
) -> None:
    await publicador.publicar(
        EventoAuditable(
            evento_id=uuid4(),
            empresa_id=empresa_id,
            ocurrido_en=ahora,
            modulo=Modulo.MASTER_DATA,
            accion=accion,
            entidad_afectada=f"cliente:{cliente_id}",
            resultado=Resultado.COMPLETADO,
            usuario_id=usuario_id,
            direccion_ip=direccion_ip,
        )
    )


class ListarClientes:
    """The catalogue of PAN-DM-01: name, CUIT, origin, WhatsApp and status."""

    def __init__(self, *, clientes: PortRepositorioCliente) -> None:
        self._clientes = clientes

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        rol: RolUsuario,
        filtros: FiltrosDeCliente | None = None,
        pagina: Pagina | None = None,
    ) -> ListadoDeClientes:
        exigir_lectura(rol)
        encontrados, total = await self._clientes.listar(
            empresa_id=empresa_id,
            filtros=filtros or FiltrosDeCliente(),
            pagina=pagina or Pagina(),
        )
        return ListadoDeClientes(clientes=tuple(encontrados), total=total)


class RegistrarCliente:
    """Create a client from the panel (RN-04: usable by the other modules at once)."""

    def __init__(
        self,
        *,
        clientes: PortRepositorioCliente,
        padron: PortPadron,
        publicador: PublicadorDeEventos,
        reloj: Reloj,
    ) -> None:
        self._clientes = clientes
        self._padron = padron
        self._publicador = publicador
        self._reloj = reloj

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        datos: DatosDeCliente,
        direccion_ip: str | None = None,
    ) -> VistaDeCliente:
        """`origen` is `PANEL` and is not a parameter: this use case *is* the panel.

        The duplicate CUIT of RN-03 is not checked here. `agregar` raises
        `ClienteDuplicado` from the unique index, which is the only check that cannot lose
        a race with a second tab.
        """
        exigir_escritura(rol)
        fiscales = await _resolver_datos_fiscales(self._padron, empresa_id=empresa_id, datos=datos)
        whatsapp, email = _contacto(datos)
        ahora = self._reloj.ahora()
        cliente = Cliente.registrar(
            id=uuid4(),
            empresa_id=empresa_id,
            nombre=_nombre_elegido(datos, fiscales),
            origen=OrigenDato.PANEL,
            momento=ahora,
            cuit=fiscales.cuit,
            condicion_iva=fiscales.condicion_iva,
            contacto_whatsapp=whatsapp,
            contacto_email=email,
        )
        await self._clientes.agregar(cliente)
        await _auditar(
            self._publicador,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            ahora=ahora,
            accion=ACCION_REGISTRADO,
            cliente_id=cliente.id,
            direccion_ip=direccion_ip,
        )
        return VistaDeCliente(cliente, fiscales.validacion)


def _nombre_elegido(datos: DatosDeCliente, fiscales: DatosFiscalesResueltos) -> str:
    """What the user typed, or failing that what ARCA calls this taxpayer."""
    escrito = datos.nombre.strip() if datos.nombre else ""
    if escrito:
        return escrito
    if fiscales.razon_social:
        return fiscales.razon_social
    raise EntradaInvalida("El nombre del cliente es obligatorio")


class EditarCliente:
    """Change a client's data. `origen` is not among the things that can change."""

    def __init__(
        self,
        *,
        clientes: PortRepositorioCliente,
        padron: PortPadron,
        publicador: PublicadorDeEventos,
        reloj: Reloj,
    ) -> None:
        self._clientes = clientes
        self._padron = padron
        self._publicador = publicador
        self._reloj = reloj

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        cliente_id: UUID,
        datos: DatosDeCliente,
        direccion_ip: str | None = None,
    ) -> VistaDeCliente:
        """The registry is asked **only when the CUIT changed**.

        Re-asking on every save would spend a request at ARCA to rename a client, and the
        answer is already stored. It also means an edit keeps working while ARCA is down,
        which is the behaviour somebody fixing a typo in a phone number expects.
        """
        exigir_escritura(rol)
        cliente = await self._clientes.buscar_por_id(cliente_id)
        if cliente is None:
            raise ClienteNoEncontrado(f"No existe el cliente {cliente_id}")
        fiscales = await _resolver_si_cambio(
            self._padron, empresa_id=empresa_id, datos=datos, cliente=cliente
        )
        whatsapp, email = _contacto(datos)
        ahora = self._reloj.ahora()
        cliente.renombrar(_nombre_para_edicion(datos, cliente), ahora)
        cliente.actualizar_datos_fiscales(
            cuit=fiscales.cuit, condicion_iva=fiscales.condicion_iva, momento=ahora
        )
        cliente.actualizar_contacto(contacto_whatsapp=whatsapp, contacto_email=email, momento=ahora)
        await self._clientes.guardar(cliente)
        await _auditar(
            self._publicador,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            ahora=ahora,
            accion=ACCION_EDITADO,
            cliente_id=cliente.id,
            direccion_ip=direccion_ip,
        )
        return VistaDeCliente(cliente, fiscales.validacion)


async def _resolver_si_cambio(
    padron: PortPadron, *, empresa_id: EmpresaId, datos: DatosDeCliente, cliente: Cliente
) -> DatosFiscalesResueltos:
    entrante = "".join(c for c in (datos.cuit or "") if c.isdigit())
    actual = str(cliente.cuit) if cliente.cuit else ""
    if entrante and entrante == actual:
        return DatosFiscalesResueltos(cliente.cuit, datos.condicion_iva, None, None)
    return await _resolver_datos_fiscales(padron, empresa_id=empresa_id, datos=datos)


def _nombre_para_edicion(datos: DatosDeCliente, cliente: Cliente) -> str:
    """An edit never silently renames: what is already there stays unless replaced.

    Which is why the registry's razón social does not reach this function even when the
    lookup returned one. `RegistrarCliente` may fall back to it because there is nothing
    to overwrite; an edit always has a name already, chosen by somebody.
    """
    escrito = datos.nombre.strip() if datos.nombre else ""
    return escrito or cliente.nombre


class CambiarEstadoDeCliente:
    """Deactivate or reactivate. The «estado» column of the listing."""

    def __init__(
        self,
        *,
        clientes: PortRepositorioCliente,
        publicador: PublicadorDeEventos,
        reloj: Reloj,
    ) -> None:
        self._clientes = clientes
        self._publicador = publicador
        self._reloj = reloj

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        cliente_id: UUID,
        activo: bool,
        direccion_ip: str | None = None,
    ) -> VistaDeCliente:
        exigir_escritura(rol)
        cliente = await self._clientes.buscar_por_id(cliente_id)
        if cliente is None:
            raise ClienteNoEncontrado(f"No existe el cliente {cliente_id}")
        ahora = self._reloj.ahora()
        if activo:
            cliente.reactivar(ahora)
        else:
            cliente.desactivar(ahora)
        await self._clientes.guardar(cliente)
        await _auditar(
            self._publicador,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            ahora=ahora,
            accion=ACCION_REACTIVADO if activo else ACCION_DESACTIVADO,
            cliente_id=cliente.id,
            direccion_ip=direccion_ip,
        )
        return VistaDeCliente(cliente)


__all__ = [
    "CambiarEstadoDeCliente",
    "DatosDeCliente",
    "EditarCliente",
    "ListarClientes",
    "RegistrarCliente",
    "VistaDeCliente",
]
