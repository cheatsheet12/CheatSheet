"""The plan to correct names stored before normalization existed (HU-E4-05 RN-09).

`planificar_correccion` is a pure function: it receives what is stored and says what to
change and what to leave alone, with the reason. It writes nothing and reads no clock,
which is what lets the dry-run report and the real run share exactly one decision.

Three things are never changed, and each carries its reason:

- a **category** that would collide with another one of the same company and scope
  (`COLISION_DE_CATEGORIA`): the unique index would refuse it, and picking a winner is not
  this function's call;
- a name that would be **invalid** after normalizing (`NOMBRE_INVALIDO`): empty, or longer
  than the aggregate allows (`str.lower()` expands «İ» into two characters);
- a **service whose duration is out of range** (`DURACION_FUERA_DE_REGLA`): the CHECK of
  migration 0025 is `NOT VALID` but PostgreSQL still demands it on every `UPDATE` of the
  row, so renaming such a service would abort the whole transaction.

A CUIT can never collide: the correction does not touch it.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from cheatsheet.contexts.master_data.domain import categoria, cliente, servicio
from cheatsheet.contexts.master_data.domain.normalizacion import (
    normalizar_nombre_de_catalogo,
    normalizar_nombre_de_cliente,
)
from cheatsheet.contexts.master_data.domain.valores import AmbitoDeCategoria
from cheatsheet.shared.fiscal import CUIT


class EntidadCorregible(StrEnum):
    CLIENTE = "CLIENTE"
    SERVICIO = "SERVICIO"
    CATEGORIA = "CATEGORIA"


class MotivoDeOmision(StrEnum):
    COLISION_DE_CATEGORIA = "COLISION_DE_CATEGORIA"
    NOMBRE_INVALIDO = "NOMBRE_INVALIDO"
    DURACION_FUERA_DE_REGLA = "DURACION_FUERA_DE_REGLA"


_LARGO_MAXIMO = {
    EntidadCorregible.CLIENTE: cliente.LARGO_MAXIMO_NOMBRE,
    EntidadCorregible.SERVICIO: servicio.LARGO_MAXIMO_NOMBRE,
    EntidadCorregible.CATEGORIA: categoria.LARGO_MAXIMO_NOMBRE,
}


@dataclass(frozen=True, slots=True)
class NombreRegistrado:
    """What is stored for one row, as read: the name is **not** normalized."""

    entidad: EntidadCorregible
    id: UUID
    nombre: str
    cuit: CUIT | None = None
    aplica_a: AmbitoDeCategoria | None = None
    #: Only meaningful for a service: whether the row satisfies the rule of migration 0025.
    duracion_valida: bool = True


@dataclass(frozen=True, slots=True)
class Cambio:
    entidad: EntidadCorregible
    id: UUID
    original: str
    normalizado: str


@dataclass(frozen=True, slots=True)
class Omision:
    entidad: EntidadCorregible
    id: UUID
    original: str
    normalizado: str
    motivo: MotivoDeOmision


@dataclass(frozen=True, slots=True)
class PlanDeCorreccion:
    cambios: tuple[Cambio, ...]
    omisiones: tuple[Omision, ...]

    def conteos(self) -> Mapping[str, int]:
        """Counts only: this is what reaches the audit log, which never carries a name."""

        def cambios_de(entidad: EntidadCorregible) -> int:
            return sum(1 for c in self.cambios if c.entidad is entidad)

        def omitidos(motivo: MotivoDeOmision) -> int:
            return sum(1 for o in self.omisiones if o.motivo is motivo)

        return {
            "clientes": cambios_de(EntidadCorregible.CLIENTE),
            "servicios": cambios_de(EntidadCorregible.SERVICIO),
            "categorias": cambios_de(EntidadCorregible.CATEGORIA),
            "omitidos_colision": omitidos(MotivoDeOmision.COLISION_DE_CATEGORIA),
            "omitidos_nombre_invalido": omitidos(MotivoDeOmision.NOMBRE_INVALIDO),
            "omitidos_duracion": omitidos(MotivoDeOmision.DURACION_FUERA_DE_REGLA),
        }


def _normalizar(registro: NombreRegistrado) -> str:
    if registro.entidad is EntidadCorregible.CLIENTE:
        return normalizar_nombre_de_cliente(registro.nombre, registro.cuit)
    return normalizar_nombre_de_catalogo(registro.nombre)


def _motivo_de_rechazo(registro: NombreRegistrado, normalizado: str) -> MotivoDeOmision | None:
    if not normalizado or len(normalizado) > _LARGO_MAXIMO[registro.entidad]:
        return MotivoDeOmision.NOMBRE_INVALIDO
    if registro.entidad is EntidadCorregible.SERVICIO and not registro.duracion_valida:
        return MotivoDeOmision.DURACION_FUERA_DE_REGLA
    return None


def _clave_de_categoria(registro: NombreRegistrado, nombre: str) -> tuple[str, AmbitoDeCategoria]:
    # `aplica_a` is always present for a category; `AMBOS` only satisfies the type checker.
    return (nombre.lower(), registro.aplica_a or AmbitoDeCategoria.AMBOS)


def planificar_correccion(registros: Iterable[NombreRegistrado]) -> PlanDeCorreccion:
    """What to change and what to leave, over one company's stored names."""
    cambios: list[Cambio] = []
    omisiones: list[Omision] = []
    # Every category lands in its final key: the normalized name if it changes, the stored
    # one if it stays (unchanged or omitted). More than one row in a key is a collision.
    grupos: dict[tuple[str, AmbitoDeCategoria], list[Cambio]] = defaultdict(list)
    ocupadas: dict[tuple[str, AmbitoDeCategoria], int] = defaultdict(int)

    for registro in registros:
        normalizado = _normalizar(registro)
        es_categoria = registro.entidad is EntidadCorregible.CATEGORIA
        if normalizado == registro.nombre:
            if es_categoria:
                ocupadas[_clave_de_categoria(registro, registro.nombre)] += 1
            continue
        motivo = _motivo_de_rechazo(registro, normalizado)
        if motivo is not None:
            omisiones.append(
                Omision(registro.entidad, registro.id, registro.nombre, normalizado, motivo)
            )
            if es_categoria:
                ocupadas[_clave_de_categoria(registro, registro.nombre)] += 1
            continue
        cambio = Cambio(registro.entidad, registro.id, registro.nombre, normalizado)
        if es_categoria:
            clave = _clave_de_categoria(registro, normalizado)
            grupos[clave].append(cambio)
        else:
            cambios.append(cambio)

    for clave, candidatas in grupos.items():
        if len(candidatas) + ocupadas[clave] > 1:
            omisiones.extend(
                Omision(
                    c.entidad,
                    c.id,
                    c.original,
                    c.normalizado,
                    MotivoDeOmision.COLISION_DE_CATEGORIA,
                )
                for c in candidatas
            )
        else:
            cambios.extend(candidatas)
    return PlanDeCorreccion(cambios=tuple(cambios), omisiones=tuple(omisiones))
