"""Correcting the names stored before normalization existed (HU-E4-05 RN-09).

Four use cases over one port: report what would change, apply it, restore a run, list the
runs. All of them are for the **Administrador** only — it is a bulk write over the whole
catalogue of the company, the kind of operation this system already reserves to that role.

**The audit log carries counts and never a name.** The log is stored forever in a table
nobody can update or delete, so a client's name written there could never be erased. The
names live in the backup table, behind the same row-level security as the table they came
from, and in the dry-run report, which only the Administrador of that company sees.

Applying and restoring take the company's turn first (`tomar_turno`): two corrections
running at once would both read the same names and race for the same rows.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID, uuid4

from cheatsheet.contexts.master_data.application.autorizacion import exigir_administrador
from cheatsheet.contexts.master_data.application.errors import (
    CorreccionEnCurso,
    CorridaNoEncontrada,
)
from cheatsheet.contexts.master_data.application.ports import (
    PortCorreccionDeNombres,
    ResumenDeCorrida,
)
from cheatsheet.contexts.master_data.domain.correccion import (
    Cambio,
    EntidadCorregible,
    MotivoDeOmision,
    PlanDeCorreccion,
    planificar_correccion,
)
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.clock import Reloj
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.roles import RolUsuario

ACCION_APLICADA = "correccion_de_datos_aplicada"
ACCION_RESTAURADA = "correccion_de_datos_restaurada"

EJEMPLOS_POR_ENTIDAD = 5

MENSAJE_EN_CURSO = "Ya hay una correccion o restauracion en curso para esta empresa."


@dataclass(frozen=True, slots=True)
class Ejemplo:
    """One «before → after» pair. Shown to the Administrador only, never logged."""

    antes: str
    despues: str


@dataclass(frozen=True, slots=True)
class InformeDeCorreccion:
    a_corregir: Mapping[EntidadCorregible, int]
    omitidos: Mapping[MotivoDeOmision, int]
    ejemplos: Mapping[EntidadCorregible, tuple[Ejemplo, ...]]


@dataclass(frozen=True, slots=True)
class ResultadoDeCorreccion:
    corrida_id: UUID
    conteos: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class ResultadoDeRestauracion:
    restaurados: int
    conservados: int


def _informe(plan: PlanDeCorreccion) -> InformeDeCorreccion:
    ejemplos: dict[EntidadCorregible, tuple[Ejemplo, ...]] = {}
    a_corregir: dict[EntidadCorregible, int] = {}
    for entidad in EntidadCorregible:
        propios = [c for c in plan.cambios if c.entidad is entidad]
        a_corregir[entidad] = len(propios)
        ejemplos[entidad] = tuple(
            Ejemplo(antes=c.original, despues=c.normalizado) for c in propios[:EJEMPLOS_POR_ENTIDAD]
        )
    omitidos = {
        motivo: sum(1 for o in plan.omisiones if o.motivo is motivo) for motivo in MotivoDeOmision
    }
    return InformeDeCorreccion(a_corregir=a_corregir, omitidos=omitidos, ejemplos=ejemplos)


async def _auditar(
    publicador: PublicadorDeEventos,
    reloj: Reloj,
    *,
    empresa_id: EmpresaId,
    usuario_id: UsuarioId,
    accion: str,
    corrida_id: UUID,
    detalle: Mapping[str, str],
    direccion_ip: str | None,
) -> None:
    await publicador.publicar(
        EventoAuditable(
            evento_id=uuid4(),
            empresa_id=empresa_id,
            ocurrido_en=reloj.ahora(),
            modulo=Modulo.MASTER_DATA,
            accion=accion,
            entidad_afectada=f"correccion:{corrida_id}",
            resultado=Resultado.COMPLETADO,
            usuario_id=usuario_id,
            direccion_ip=direccion_ip,
            detalle=detalle,
        )
    )


async def _exigir_turno(correccion: PortCorreccionDeNombres) -> None:
    if not await correccion.tomar_turno():
        raise CorreccionEnCurso(MENSAJE_EN_CURSO)


class InformarCorreccion:
    """The dry-run: counts, a few examples and what will not be touched. Writes nothing."""

    def __init__(self, *, correccion: PortCorreccionDeNombres) -> None:
        self._correccion = correccion

    async def ejecutar(self, *, empresa_id: EmpresaId, rol: RolUsuario) -> InformeDeCorreccion:
        del empresa_id  # The company is the RLS context of the port's session.
        exigir_administrador(rol)
        plan = planificar_correccion(await self._correccion.leer_nombres())
        return _informe(plan)


class AplicarCorreccion:
    """Write the new names and their backup in one transaction, and log the counts."""

    def __init__(
        self,
        *,
        correccion: PortCorreccionDeNombres,
        publicador: PublicadorDeEventos,
        reloj: Reloj,
    ) -> None:
        self._correccion = correccion
        self._publicador = publicador
        self._reloj = reloj

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        direccion_ip: str | None = None,
    ) -> ResultadoDeCorreccion:
        exigir_administrador(rol)
        await _exigir_turno(self._correccion)
        plan = planificar_correccion(await self._correccion.leer_nombres())
        corrida_id = uuid4()
        aplicados = await self._correccion.aplicar(corrida_id, plan.cambios, self._reloj.ahora())
        conteos = _conteos_aplicados(plan, aplicados)
        await _auditar(
            self._publicador,
            self._reloj,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            accion=ACCION_APLICADA,
            corrida_id=corrida_id,
            detalle={clave: str(valor) for clave, valor in conteos.items()},
            direccion_ip=direccion_ip,
        )
        return ResultadoDeCorreccion(corrida_id=corrida_id, conteos=conteos)


_CLAVE_DE_CONTEO = {
    EntidadCorregible.CLIENTE: "clientes",
    EntidadCorregible.SERVICIO: "servicios",
    EntidadCorregible.CATEGORIA: "categorias",
}


def _conteos_aplicados(plan: PlanDeCorreccion, aplicados: Sequence[Cambio]) -> Mapping[str, int]:
    """The plan's omissions, plus what was actually written and what was dropped on the way.

    A change is dropped when the row was edited between reading and writing, or when the
    unique index refused a category: either way it is not counted as applied.
    """
    conteos = dict(plan.conteos())
    for clave in _CLAVE_DE_CONTEO.values():
        conteos[clave] = 0
    for cambio in aplicados:
        conteos[_CLAVE_DE_CONTEO[cambio.entidad]] += 1
    conteos["no_aplicados"] = len(plan.cambios) - len(aplicados)
    return conteos


class RestaurarCorreccion:
    """Put a run's original names back, without overwriting what was edited afterwards."""

    def __init__(
        self,
        *,
        correccion: PortCorreccionDeNombres,
        publicador: PublicadorDeEventos,
        reloj: Reloj,
    ) -> None:
        self._correccion = correccion
        self._publicador = publicador
        self._reloj = reloj

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        corrida_id: UUID,
        direccion_ip: str | None = None,
    ) -> ResultadoDeRestauracion:
        exigir_administrador(rol)
        await _exigir_turno(self._correccion)
        if not await self._correccion.existe_corrida(corrida_id):
            raise CorridaNoEncontrada("No existe esa correccion en esta empresa.")
        restaurados, conservados = await self._correccion.restaurar(corrida_id)
        await _auditar(
            self._publicador,
            self._reloj,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            accion=ACCION_RESTAURADA,
            corrida_id=corrida_id,
            detalle={"restaurados": str(restaurados), "conservados": str(conservados)},
            direccion_ip=direccion_ip,
        )
        return ResultadoDeRestauracion(restaurados=restaurados, conservados=conservados)


class ListarCorridas:
    """The runs of this company, newest first, for the screen's «Restaurar» list."""

    def __init__(self, *, correccion: PortCorreccionDeNombres) -> None:
        self._correccion = correccion

    async def ejecutar(
        self, *, empresa_id: EmpresaId, rol: RolUsuario
    ) -> tuple[ResumenDeCorrida, ...]:
        del empresa_id
        exigir_administrador(rol)
        return tuple(await self._correccion.listar_corridas())
