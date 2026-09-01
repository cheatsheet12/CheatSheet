"""Categories and the classification of what they label (HU-E4-03, HU-E4-04).

Two stories in one module because they are two halves of one mechanism: a category that
classifies nothing is a label nobody uses, and an assignment needs a category to point at.

**The scope check is the load-bearing rule** (HU-E4-04 RN-01). The screen only *hides*
what does not fit — the acceptance criterion is «el sistema no ofrece esa categoría» — and
hiding is not refusing. What refuses is `exigir_admite_cliente` on the aggregate, called
from here, which is also what will refuse when epic 8's agent classifies through no form.

**The category is always read before it is used**, and that is the barrier that keeps one
company from classifying with another's category. A foreign key is verified with the table
owner's permissions and therefore sees rows Row-Level Security hides; this `SELECT` does
not, so a foreign category is simply not found.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID, uuid4

from cheatsheet.contexts.master_data.application.autorizacion import (
    exigir_escritura,
    exigir_lectura,
)
from cheatsheet.contexts.master_data.application.errors import (
    CategoriaDuplicada,
    CategoriaNoEncontrada,
    ClienteNoEncontrado,
    ServicioNoEncontrado,
)
from cheatsheet.contexts.master_data.application.ports import (
    PortClasificaciones,
    PortRepositorioCategoria,
    PortRepositorioCliente,
    PortRepositorioServicio,
)
from cheatsheet.contexts.master_data.domain.categoria import (
    MENSAJE_DUPLICADA,
    CategoriaEmpresa,
)
from cheatsheet.contexts.master_data.domain.valores import AmbitoDeCategoria
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.clock import Reloj
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.roles import RolUsuario

ACCION_REGISTRADA = "categoria_registrada"
ACCION_RENOMBRADA = "categoria_renombrada"
ACCION_ELIMINADA = "categoria_eliminada"
ACCION_CLASIFICADO = "elemento_clasificado"
ACCION_DESCLASIFICADO = "elemento_desclasificado"


async def _auditar(
    publicador: PublicadorDeEventos,
    *,
    empresa_id: EmpresaId,
    usuario_id: UsuarioId | None,
    ahora: datetime,
    accion: str,
    entidad: str,
    direccion_ip: str | None,
) -> None:
    await publicador.publicar(
        EventoAuditable(
            evento_id=uuid4(),
            empresa_id=empresa_id,
            ocurrido_en=ahora,
            modulo=Modulo.MASTER_DATA,
            accion=accion,
            entidad_afectada=entidad,
            resultado=Resultado.COMPLETADO,
            usuario_id=usuario_id,
            direccion_ip=direccion_ip,
        )
    )


class ListarCategorias:
    """PAN-DM-03, and the dropdowns of PAN-DM-01 and PAN-DM-02.

    The same use case serves the three because `aplica_a` filters by usability: asking for
    `CLIENTE` also returns the `AMBOS` ones, which is exactly what the client form needs
    to offer.
    """

    def __init__(self, *, categorias: PortRepositorioCategoria) -> None:
        self._categorias = categorias

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        rol: RolUsuario,
        aplica_a: AmbitoDeCategoria | None = None,
    ) -> Sequence[CategoriaEmpresa]:
        exigir_lectura(rol)
        return await self._categorias.listar(empresa_id=empresa_id, aplica_a=aplica_a)


class RegistrarCategoria:
    """Create one, refusing a name already used in the same scope (RN-02)."""

    def __init__(
        self,
        *,
        categorias: PortRepositorioCategoria,
        publicador: PublicadorDeEventos,
        reloj: Reloj,
    ) -> None:
        self._categorias = categorias
        self._publicador = publicador
        self._reloj = reloj

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        nombre: str,
        aplica_a: AmbitoDeCategoria,
        direccion_ip: str | None = None,
    ) -> CategoriaEmpresa:
        exigir_escritura(rol)
        await _exigir_nombre_libre(self._categorias, nombre=nombre, aplica_a=aplica_a)
        ahora = self._reloj.ahora()
        categoria = CategoriaEmpresa.registrar(
            id=uuid4(),
            empresa_id=empresa_id,
            nombre=nombre,
            aplica_a=aplica_a,
            momento=ahora,
        )
        await self._categorias.agregar(categoria)
        await _auditar(
            self._publicador,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            ahora=ahora,
            accion=ACCION_REGISTRADA,
            entidad=f"categoria:{categoria.id}",
            direccion_ip=direccion_ip,
        )
        return categoria


async def _exigir_nombre_libre(
    categorias: PortRepositorioCategoria,
    *,
    nombre: str,
    aplica_a: AmbitoDeCategoria,
    excepto: UUID | None = None,
) -> None:
    """RN-02, named before the unique index has to stop it.

    Same arrangement as the duplicate CUIT of `catalogo-de-clientes`: the index is what
    *prevents* the duplicate — it cannot lose a race — and this lookup is what lets the
    message be the one the story asks for.
    """
    existente = await categorias.buscar_por_nombre_y_ambito(nombre=nombre, aplica_a=aplica_a)
    if existente is not None and existente.id != excepto:
        raise CategoriaDuplicada(MENSAJE_DUPLICADA)


class EditarCategoria:
    """Rename, or change the scope. Both go through the aggregate's own operations."""

    def __init__(
        self,
        *,
        categorias: PortRepositorioCategoria,
        publicador: PublicadorDeEventos,
        reloj: Reloj,
    ) -> None:
        self._categorias = categorias
        self._publicador = publicador
        self._reloj = reloj

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        categoria_id: UUID,
        nombre: str,
        aplica_a: AmbitoDeCategoria,
        direccion_ip: str | None = None,
    ) -> CategoriaEmpresa:
        exigir_escritura(rol)
        categoria = await self._categorias.buscar_por_id(categoria_id)
        if categoria is None:
            raise CategoriaNoEncontrada(f"No existe la categoria {categoria_id}")
        await _exigir_nombre_libre(
            self._categorias, nombre=nombre, aplica_a=aplica_a, excepto=categoria_id
        )
        categoria.renombrar(nombre)
        categoria.cambiar_ambito(aplica_a)
        await self._categorias.guardar(categoria)
        await _auditar(
            self._publicador,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            ahora=self._reloj.ahora(),
            accion=ACCION_RENOMBRADA,
            entidad=f"categoria:{categoria.id}",
            direccion_ip=direccion_ip,
        )
        return categoria


class EliminarCategoria:
    """RN-03: the classified elements lose the label and nothing else.

    That is a cascade on the two link tables and nothing more — there is no business data
    living on the association. It is the one delete `master_data` performs.
    """

    def __init__(
        self,
        *,
        categorias: PortRepositorioCategoria,
        publicador: PublicadorDeEventos,
        reloj: Reloj,
    ) -> None:
        self._categorias = categorias
        self._publicador = publicador
        self._reloj = reloj

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        categoria_id: UUID,
        direccion_ip: str | None = None,
    ) -> None:
        exigir_escritura(rol)
        categoria = await self._categorias.buscar_por_id(categoria_id)
        if categoria is None:
            raise CategoriaNoEncontrada(f"No existe la categoria {categoria_id}")
        await self._categorias.eliminar(categoria_id)
        await _auditar(
            self._publicador,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            ahora=self._reloj.ahora(),
            accion=ACCION_ELIMINADA,
            entidad=f"categoria:{categoria_id}",
            direccion_ip=direccion_ip,
        )


class ClasificarCliente:
    """Assign or remove a category on a client (HU-E4-04)."""

    def __init__(
        self,
        *,
        clientes: PortRepositorioCliente,
        categorias: PortRepositorioCategoria,
        clasificaciones: PortClasificaciones,
        publicador: PublicadorDeEventos,
        reloj: Reloj,
    ) -> None:
        self._clientes = clientes
        self._categorias = categorias
        self._clasificaciones = clasificaciones
        self._publicador = publicador
        self._reloj = reloj

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        cliente_id: UUID,
        categoria_id: UUID,
        asignar: bool,
        direccion_ip: str | None = None,
    ) -> Sequence[CategoriaEmpresa]:
        exigir_escritura(rol)
        if await self._clientes.buscar_por_id(cliente_id) is None:
            raise ClienteNoEncontrado(f"No existe el cliente {cliente_id}")
        categoria = await self._categorias.buscar_por_id(categoria_id)
        if categoria is None:
            raise CategoriaNoEncontrada(f"No existe la categoria {categoria_id}")
        if asignar:
            categoria.exigir_admite_cliente()
            await self._clasificaciones.asignar_a_cliente(
                cliente_id=cliente_id, categoria_id=categoria_id
            )
        else:
            # No scope check when removing: a classification that exists has to be
            # removable even if the category's scope was narrowed afterwards.
            await self._clasificaciones.quitar_de_cliente(
                cliente_id=cliente_id, categoria_id=categoria_id
            )
        await _auditar(
            self._publicador,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            ahora=self._reloj.ahora(),
            accion=ACCION_CLASIFICADO if asignar else ACCION_DESCLASIFICADO,
            entidad=f"cliente:{cliente_id}",
            direccion_ip=direccion_ip,
        )
        return await self._clasificaciones.categorias_de_cliente(cliente_id)


class ClasificarServicio:
    """The same, on a service. Separate use case because the guard it calls is different."""

    def __init__(
        self,
        *,
        servicios: PortRepositorioServicio,
        categorias: PortRepositorioCategoria,
        clasificaciones: PortClasificaciones,
        publicador: PublicadorDeEventos,
        reloj: Reloj,
    ) -> None:
        self._servicios = servicios
        self._categorias = categorias
        self._clasificaciones = clasificaciones
        self._publicador = publicador
        self._reloj = reloj

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        servicio_id: UUID,
        categoria_id: UUID,
        asignar: bool,
        direccion_ip: str | None = None,
    ) -> Sequence[CategoriaEmpresa]:
        exigir_escritura(rol)
        if await self._servicios.buscar_por_id(servicio_id) is None:
            raise ServicioNoEncontrado(f"No existe el servicio {servicio_id}")
        categoria = await self._categorias.buscar_por_id(categoria_id)
        if categoria is None:
            raise CategoriaNoEncontrada(f"No existe la categoria {categoria_id}")
        if asignar:
            categoria.exigir_admite_servicio()
            await self._clasificaciones.asignar_a_servicio(
                servicio_id=servicio_id, categoria_id=categoria_id
            )
        else:
            await self._clasificaciones.quitar_de_servicio(
                servicio_id=servicio_id, categoria_id=categoria_id
            )
        await _auditar(
            self._publicador,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            ahora=self._reloj.ahora(),
            accion=ACCION_CLASIFICADO if asignar else ACCION_DESCLASIFICADO,
            entidad=f"servicio:{servicio_id}",
            direccion_ip=direccion_ip,
        )
        return await self._clasificaciones.categorias_de_servicio(servicio_id)


class VerClasificacion:
    """What an element already carries, for the control that is about to change it.

    A read use case of its own rather than a return value of the write one, because the
    screen needs the state **before** touching anything: the checkboxes have to open
    already ticked. `ClasificarCliente` returns the new set, which is the other half.
    """

    def __init__(self, *, clasificaciones: PortClasificaciones) -> None:
        self._clasificaciones = clasificaciones

    async def de_cliente(self, *, cliente_id: UUID, rol: RolUsuario) -> Sequence[CategoriaEmpresa]:
        exigir_lectura(rol)
        return await self._clasificaciones.categorias_de_cliente(cliente_id)

    async def de_servicio(
        self, *, servicio_id: UUID, rol: RolUsuario
    ) -> Sequence[CategoriaEmpresa]:
        exigir_lectura(rol)
        return await self._clasificaciones.categorias_de_servicio(servicio_id)
