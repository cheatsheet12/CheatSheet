"""Los casos de uso de recursos reservables (HU-E7-04 y HU-E7-05).

**Sólo el Administrador configura recursos**, que es lo que dicen las dos historias; todos los
roles los leen, porque el listado es lo que hace legible la agenda de HU-E7-01. Los guardas
viven acá y no sólo en el router, por lo que enseñó PRU-09.

La disponibilidad se **reemplaza entera** en vez de editarse franja por franja. Un horario de
atención es un objeto chico y coherente: guardarlo por partes obliga a decidir qué pasa
cuando una franja nueva pisa a otra vieja, y esa decisión no la pide ninguna historia.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from cheatsheet.contexts.scheduling.application.errors import (
    ExcepcionDuplicada,
    RecursoInexistente,
)
from cheatsheet.contexts.scheduling.application.ports import PortRepositorioRecurso
from cheatsheet.contexts.scheduling.domain.recurso import (
    MENSAJE_EXCEPCION_DUPLICADA,
    ExcepcionDeDisponibilidad,
    PatronDeDisponibilidad,
    RecursoReservable,
    TipoRecurso,
)
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.roles import RolUsuario

MOTIVO_SOLO_ADMIN = "Solo un Administrador puede configurar recursos reservables"


def _exigir_administrador(rol: RolUsuario) -> None:
    if rol is not RolUsuario.ADMINISTRADOR:
        raise EntradaInvalida(MOTIVO_SOLO_ADMIN)


class ListarRecursos:
    """PAN-AGE-03. Todos los roles leen: sin recursos no se entiende la agenda."""

    def __init__(self, recursos: PortRepositorioRecurso) -> None:
        self._recursos = recursos

    async def ejecutar(self, *, solo_activos: bool = False) -> list[RecursoReservable]:
        return await self._recursos.listar(solo_activos=solo_activos)


class VerRecurso:
    """Levanta en vez de devolver `None`: bajo RLS «no es tuyo» y «no existe» son lo mismo."""

    def __init__(self, recursos: PortRepositorioRecurso) -> None:
        self._recursos = recursos

    async def ejecutar(self, recurso_id: UUID) -> RecursoReservable:
        recurso = await self._recursos.buscar_por_id(recurso_id)
        if recurso is None:
            raise RecursoInexistente("El recurso no existe")
        return recurso


class RegistrarRecurso:
    """HU-E7-04, primer criterio: nombre, tipo, servicios asociados y disponibilidad.

    Un recurso nace **activo y sin servicios**, y eso es deliberado: `admite_servicio` devuelve
    `False` para todo mientras la lista esté vacía, así que un recurso a medio configurar no
    acepta reservas en lugar de aceptar cualquiera.
    """

    def __init__(self, recursos: PortRepositorioRecurso, publicador: PublicadorDeEventos) -> None:
        self._recursos = recursos
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        nombre: str,
        tipo: TipoRecurso,
        ahora: datetime,
        patrones: tuple[PatronDeDisponibilidad, ...] = (),
        servicios: frozenset[UUID] = frozenset(),
    ) -> RecursoReservable:
        _exigir_administrador(rol)
        recurso = RecursoReservable(
            id=uuid4(),
            empresa_id=empresa_id,
            nombre=nombre.strip(),
            tipo=tipo,
            patrones=tuple(patrones),
            servicios=servicios,
            created_at=ahora,
        )
        await self._recursos.agregar(recurso)
        await _auditar(
            self._publicador, empresa_id, usuario_id, recurso, "registrar_recurso", ahora
        )
        return recurso


class ConfigurarDisponibilidad:
    """HU-E7-04 RN-01. Reemplaza el horario semanal entero.

    La franja invertida la rechaza el propio `PatronDeDisponibilidad` al construirse, con la
    frase de la historia. No se revalida acá: dos lugares que validan lo mismo son dos lugares
    que pueden dejar de estar de acuerdo.
    """

    def __init__(self, recursos: PortRepositorioRecurso, publicador: PublicadorDeEventos) -> None:
        self._recursos = recursos
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        recurso_id: UUID,
        patrones: tuple[PatronDeDisponibilidad, ...],
        ahora: datetime,
    ) -> RecursoReservable:
        _exigir_administrador(rol)
        recurso = await VerRecurso(self._recursos).ejecutar(recurso_id)
        recurso.definir_disponibilidad(patrones)
        await self._recursos.guardar(recurso)
        await _auditar(
            self._publicador, empresa_id, usuario_id, recurso, "configurar_disponibilidad", ahora
        )
        return recurso


class AsociarServicios:
    """HU-E7-04 RN-02. Reemplaza la lista de servicios que se prestan en el recurso.

    No se verifica acá que cada servicio exista y sea agendable, y es una decisión: el filtro
    que importa es el de `ReservarTurno`, que es donde un servicio mal asociado haría daño.
    Validar también acá obligaría a `scheduling` a consultar `master_data` en una operación de
    configuración, y dejaría la lista sin poder guardarse el día que ese contexto no responde.
    """

    def __init__(self, recursos: PortRepositorioRecurso, publicador: PublicadorDeEventos) -> None:
        self._recursos = recursos
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        recurso_id: UUID,
        servicios: frozenset[UUID],
        ahora: datetime,
    ) -> RecursoReservable:
        _exigir_administrador(rol)
        recurso = await VerRecurso(self._recursos).ejecutar(recurso_id)
        recurso.asociar_servicios(servicios)
        await self._recursos.guardar(recurso)
        await _auditar(
            self._publicador, empresa_id, usuario_id, recurso, "asociar_servicios", ahora
        )
        return recurso


class CambiarEstadoDeRecurso:
    """HU-E7-04 RN-03. Desactivar impide reservas nuevas y **no toca las viejas**.

    No hay `eliminar` y no lo va a haber: los turnos que ya se prestaron en este recurso lo
    referencian, y borrarlo dejaría la agenda histórica apuntando a nada.
    """

    def __init__(self, recursos: PortRepositorioRecurso, publicador: PublicadorDeEventos) -> None:
        self._recursos = recursos
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        recurso_id: UUID,
        activo: bool,
        ahora: datetime,
    ) -> RecursoReservable:
        _exigir_administrador(rol)
        recurso = await VerRecurso(self._recursos).ejecutar(recurso_id)
        if activo:
            recurso.activar()
        else:
            recurso.desactivar()
        await self._recursos.guardar(recurso)
        await _auditar(
            self._publicador,
            empresa_id,
            usuario_id,
            recurso,
            "activar_recurso" if activo else "desactivar_recurso",
            ahora,
        )
        return recurso


class RegistrarExcepcion:
    """HU-E7-05. Un feriado, unas vacaciones o una apertura fuera de horario.

    El rechazo por duplicado lo levanta el agregado como `InvarianteViolada`; acá se traduce a
    `ExcepcionDuplicada` para que el router pueda contestar 422 con la frase de la historia en
    lugar de un 409 cuyo detalle el BFF descarta.
    """

    def __init__(self, recursos: PortRepositorioRecurso, publicador: PublicadorDeEventos) -> None:
        self._recursos = recursos
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        recurso_id: UUID,
        excepcion: ExcepcionDeDisponibilidad,
        ahora: datetime,
    ) -> RecursoReservable:
        _exigir_administrador(rol)
        recurso = await VerRecurso(self._recursos).ejecutar(recurso_id)
        try:
            recurso.agregar_excepcion(excepcion)
        except InvarianteViolada as exc:
            raise ExcepcionDuplicada(MENSAJE_EXCEPCION_DUPLICADA) from exc
        await self._recursos.guardar(recurso)
        await _auditar(
            self._publicador, empresa_id, usuario_id, recurso, "registrar_excepcion", ahora
        )
        return recurso


class QuitarExcepcion:
    """Saca la excepción de una fecha. Es cómo se corrige una: se quita y se vuelve a agregar.

    Quitar una fecha que no tiene excepción **no falla**: el resultado deseado —que ese día no
    tenga excepción— ya se cumple, y hacer fallar la operación obligaría a la pantalla a
    consultar antes de borrar para no mostrar un error sobre algo que salió bien.
    """

    def __init__(self, recursos: PortRepositorioRecurso, publicador: PublicadorDeEventos) -> None:
        self._recursos = recursos
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        recurso_id: UUID,
        fecha: date,
        ahora: datetime,
    ) -> RecursoReservable:
        _exigir_administrador(rol)
        recurso = await VerRecurso(self._recursos).ejecutar(recurso_id)
        recurso.quitar_excepcion(fecha)
        await self._recursos.guardar(recurso)
        await _auditar(self._publicador, empresa_id, usuario_id, recurso, "quitar_excepcion", ahora)
        return recurso


async def _auditar(
    publicador: PublicadorDeEventos,
    empresa_id: EmpresaId,
    usuario_id: UsuarioId,
    recurso: RecursoReservable,
    accion: str,
    ahora: datetime,
) -> None:
    await publicador.publicar(
        EventoAuditable(
            evento_id=uuid4(),
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            ocurrido_en=ahora,
            modulo=Modulo.SCHEDULING,
            accion=accion,
            entidad_afectada=f"RecursoReservable:{recurso.id}",
            resultado=Resultado.COMPLETADO,
        )
    )


__all__ = [
    "AsociarServicios",
    "CambiarEstadoDeRecurso",
    "ConfigurarDisponibilidad",
    "ListarRecursos",
    "QuitarExcepcion",
    "RegistrarExcepcion",
    "RegistrarRecurso",
    "VerRecurso",
]
