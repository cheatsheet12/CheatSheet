"""Value objects of the identity context.

What is left here is what only `identity` creates: how a password is stored, what a
notification preference is, what accepting the terms proves. The rest — `CUIT`,
`CondicionIVA`, `Email`, `RolUsuario` — has moved to the Shared Kernel as second
contexts came to need it, and is re-exported below so no import in this context had to
change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TypeVar

from cheatsheet.shared.contacto import Email as Email
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.fiscal import CUIT as CUIT
from cheatsheet.shared.fiscal import CondicionIVA as CondicionIVA
from cheatsheet.shared.roles import RolUsuario as RolUsuario

LARGO_MINIMO_CONTRASENA = 8

_Enum = TypeVar("_Enum", bound=StrEnum)


# `CondicionIVA` now lives in the Shared Kernel and is re-exported here, for the same
# reason and by the same mechanism as `RolUsuario` below.
#
# `identity` still owns the concept — the DER enum is `condicion_iva`, it is chosen at
# step 2 of the onboarding, and `Empresa` is the aggregate that holds it. What changed is
# that `integrations` now has to *produce* one: the padrón unit reads ARCA's registry and
# translates what it finds, and that translation belongs in ARCA's Anti-Corruption Layer.
# Importing this module from there would break R3 and contradict ADR-0003. See
# `shared/fiscal.py` for the full reasoning.


# `RolUsuario` now lives in the Shared Kernel and is re-exported here.
#
# `identity` still owns the concept — the DER enum is `rol_usuario`, the three roles are
# created during invitation, and HU-E1-05's last-Administrator invariant is enforced in
# this context. What changed is that `integrations` also has to authorize (HU-E2-05 lets
# an Operador read but not connect), and importing this module from there would break R3
# and contradict ADR-0003. See `shared/roles.py` for the full reasoning.
#
# Re-exported rather than moved-and-updated so the ~100 existing imports of
# `identity.domain.valores.RolUsuario` keep working untouched.


# `CUIT` and `Email` moved to the Shared Kernel in epic 3, and are re-exported here for
# the third and fourth time by the same mechanism.
#
# `master_data` is the second context to need both: `cliente.cuit` is validated by the
# same rules as `empresa.cuit` (HU-E4-01 RN-02) and `cliente.contacto_email` is an
# address the system writes to. `master_data/domain/` may not import this module — R3 —
# so a second definition of either would be the alternative, and a second definition of
# a check digit is how two parts of one system disagree about a tax id.
#
# See `shared/fiscal.py` and `shared/contacto.py`. `identity` still owns both concepts:
# it is where the first CUIT and the first email of a company are created.


class EstadoUsuario(StrEnum):
    """Three states, where the DER has a boolean `activo`.

    A declared departure, and an extension of the DER's own gap H1 ("no invitation
    state"). Two reasons it is not laxity:

    1. PAN-USR-01 shows three states. Two of them fit in a boolean; the third does not.
    2. The invariant of HU-E1-05 RN-02 — at least one active Administrator — **must not
       count somebody invited as Administrator who has not accepted yet**. With a boolean
       that person would be `activo=True` while unable to sign in, and the company would
       believe it has an administrator that does not exist. With the enum the rule reads
       `rol is ADMINISTRADOR and estado is ACTIVO`, and there is nothing subtle left to
       reason about in the one rule that guards access to the account.
    """

    INVITADO = "INVITADO"
    ACTIVO = "ACTIVO"
    INACTIVO = "INACTIVO"


class CanalDeNotificacion(StrEnum):
    """Where a notification is delivered (HU-E1-07 RN-02: «y por qué canal»)."""

    EMAIL = "EMAIL"
    PANEL = "PANEL"


class CategoriaDeNotificacion(StrEnum):
    """What a notification is about.

    The DER declares `pref_suscripciones jsonb` and no schema, so the schema has to be
    defined somewhere; this is it. The five values are **not invented**: each one belongs
    to an epic that will emit notifications. An epic that needs a sixth adds a member
    here — a closed catalogue rather than free text, for the same reason `Modulo` is one
    in the audit log: a filter over free text silently misses the rows somebody spelled
    differently.
    """

    FACTURACION = "FACTURACION"
    COBROS = "COBROS"
    SINCRONIZACION = "SINCRONIZACION"
    AGENDA = "AGENDA"
    SISTEMA = "SISTEMA"


@dataclass(frozen=True, slots=True)
class HashDeContrasena:
    """An Argon2id digest, and a wrapper whose whole purpose is not to leak it.

    `__str__` and `__repr__` return a mask. An Argon2 digest in a log line or in a
    traceback is material for an offline attack, and the way it gets there is never a
    deliberate `print` — it is a `logger.debug("usuario=%s", usuario)` written in a
    hurry, or an exception rendering its arguments.
    """

    valor: str

    def __post_init__(self) -> None:
        if not self.valor.strip():
            raise EntradaInvalida("El hash de contrasena no puede estar vacio")

    def __str__(self) -> str:
        return "***"

    def __repr__(self) -> str:
        return "HashDeContrasena(***)"


def validar_contrasena_en_claro(contrasena: str) -> str:
    """HU-E1-01 RN-01: at least 8 characters, and no further complexity rule.

    The story is explicit that this version defines nothing else, so nothing else is
    imposed. Adding rules nobody asked for is how a form becomes hostile.
    """
    if len(contrasena) < LARGO_MINIMO_CONTRASENA:
        raise EntradaInvalida(
            f"La contrasena debe tener al menos {LARGO_MINIMO_CONTRASENA} caracteres"
        )
    return contrasena


@dataclass(frozen=True, slots=True)
class PreferenciasDeNotificacion:
    """What this user wants to be told about, and where (HU-E1-07 RN-02).

    A subscription is a **pair** — category plus channel — because RN-02 asks for both
    and someone may well want invoices by email but sync failures only in the panel.
    Modelling it as a set of pairs keeps the value object immutable without the contortion
    of a frozen mapping of frozen sets.

    Serialised to `pref_suscripciones` as `{"FACTURACION": ["EMAIL", "PANEL"], …}` rather
    than as a list of pairs, because that column will be read by a human with `psql` long
    before it is read by a report.
    """

    suscripciones: frozenset[tuple[CategoriaDeNotificacion, CanalDeNotificacion]]

    @classmethod
    def todas(cls) -> PreferenciasDeNotificacion:
        """The default for a new account: opted in everywhere.

        Someone who just created an account has not been asked yet, and silence about a
        failed sync or an unpaid invoice is the worse of the two mistakes. Turning any of
        it off is one screen away.
        """
        return cls(
            frozenset(
                (categoria, canal)
                for categoria in CategoriaDeNotificacion
                for canal in CanalDeNotificacion
            )
        )

    def recibe(self, categoria: CategoriaDeNotificacion, canal: CanalDeNotificacion) -> bool:
        return (categoria, canal) in self.suscripciones

    def a_json(self) -> dict[str, list[str]]:
        return {
            categoria.value: sorted(
                canal.value for otra, canal in self.suscripciones if otra is categoria
            )
            for categoria in CategoriaDeNotificacion
        }

    @classmethod
    def desde_json(cls, crudo: object) -> PreferenciasDeNotificacion:
        """Rebuild from the column, rejecting anything the catalogue does not name.

        An unknown category or channel is not skipped quietly: the column is `jsonb` and
        accepts any shape, so this is the only place where a typo or a value left behind
        by a rolled-back deploy can still be caught.
        """
        if not isinstance(crudo, dict):
            raise EntradaInvalida("Las preferencias de notificacion deben ser un objeto")
        pares: set[tuple[CategoriaDeNotificacion, CanalDeNotificacion]] = set()
        for nombre_categoria, canales in crudo.items():
            categoria = _miembro(CategoriaDeNotificacion, nombre_categoria, "categoria")
            if not isinstance(canales, list):
                raise EntradaInvalida(f"Los canales de {categoria.value} deben ser una lista")
            for nombre_canal in canales:
                pares.add((categoria, _miembro(CanalDeNotificacion, nombre_canal, "canal")))
        return cls(frozenset(pares))


def _miembro(enumeracion: type[_Enum], valor: object, que_es: str) -> _Enum:
    # The value arrives from a `jsonb` column, so it is `object` until proven otherwise.
    # A number or a nested object is not a member name, and saying so here keeps the
    # enum from having to defend itself against types it never expects.
    if not isinstance(valor, str):
        raise EntradaInvalida(f"'{valor}' no es una {que_es} de notificacion conocida")
    try:
        return enumeracion(valor)
    except ValueError as exc:
        raise EntradaInvalida(f"'{valor}' no es una {que_es} de notificacion conocida") from exc


@dataclass(frozen=True, slots=True)
class TerminosAceptados:
    """Version and moment, always together (HU-E1-03 RN-01).

    A date without a version proves nothing about *what* was accepted, which is the only
    thing this record exists to prove.
    """

    version: str
    fecha: datetime

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise EntradaInvalida("La version de los terminos es obligatoria")
        if self.fecha.tzinfo is None:
            raise EntradaInvalida("La fecha de aceptacion debe tener zona horaria (UTC)")
