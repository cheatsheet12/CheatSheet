"""Value objects of the identity context.

`CUIT` is the important one. It is defined here and not in `billing` on purpose: it is
validated during onboarding, long before anything fiscal happens, and `cliente.cuit`
and `comprobante.receptor_cuit` will reuse the same rules. One definition of what a
well-formed CUIT is, in the context that creates the first one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TypeVar

from cheatsheet.shared.errors import EntradaInvalida

LARGO_CUIT = 11
LARGO_MINIMO_CONTRASENA = 8

# The check-digit weights ARCA uses, in order.
MULTIPLICADORES = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)

_NO_DIGITOS = re.compile(r"[^0-9]")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_Enum = TypeVar("_Enum", bound=StrEnum)


class CondicionIVA(StrEnum):
    """DER enum `condicion_iva`."""

    RESPONSABLE_INSCRIPTO = "RESPONSABLE_INSCRIPTO"
    MONOTRIBUTO = "MONOTRIBUTO"
    EXENTO = "EXENTO"
    CONSUMIDOR_FINAL = "CONSUMIDOR_FINAL"


class RolUsuario(StrEnum):
    """DER enum `rol_usuario`. Closed catalogue — HU-E1-04 RN-01: not configurable."""

    ADMINISTRADOR = "ADMINISTRADOR"
    OPERADOR = "OPERADOR"
    SOLO_LECTURA = "SOLO_LECTURA"


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
class CUIT:
    """An Argentine tax id, structurally valid.

    **Structural only, deliberately** (decision D1): format plus check digit. Whether
    the number actually exists in ARCA's registry is checked in epic 2, once the company
    has loaded its fiscal credential. Until then a well-formed but non-existent CUIT can
    enter the system — acceptable because nothing is invoiced before epic 5, and issuance
    revalidates against ARCA.

    The prefix (20/23/24/27 for people, 30/33/34 for companies) is **not** validated.
    The published lists disagree at the edges, and rejecting a real customer's CUIT is a
    worse failure than accepting one ARCA will reject later anyway.
    """

    valor: str

    def __post_init__(self) -> None:
        digitos = _NO_DIGITOS.sub("", self.valor)
        if len(digitos) != LARGO_CUIT:
            raise EntradaInvalida(f"Un CUIT tiene {LARGO_CUIT} digitos, no {len(digitos)}")
        if not _digito_verificador_valido(digitos):
            raise EntradaInvalida("El digito verificador del CUIT no es correcto")
        object.__setattr__(self, "valor", digitos)

    @property
    def formateado(self) -> str:
        """`30-71234567-8` — how a person reads it."""
        return f"{self.valor[:2]}-{self.valor[2:10]}-{self.valor[10]}"

    def __str__(self) -> str:
        return self.valor


def _digito_verificador_valido(digitos: str) -> bool:
    suma = sum(int(d) * m for d, m in zip(digitos[:10], MULTIPLICADORES, strict=True))
    resto = suma % 11
    esperado = 11 - resto
    if esperado == 11:
        esperado = 0
    elif esperado == 10:
        # 10 is never assigned as a check digit, so no CUIT can end in it.
        return False
    return esperado == int(digitos[10])


@dataclass(frozen=True, slots=True)
class Email:
    """Normalised to lowercase.

    HU-E1-01 RN-03 forbids two accounts with the same email. Comparing the raw strings
    would let `Ana@x.com` and `ana@x.com` through as two accounts, which is the same
    person and, sooner or later, the same support ticket.
    """

    valor: str

    def __post_init__(self) -> None:
        limpio = self.valor.strip().lower()
        if not _EMAIL.match(limpio):
            raise EntradaInvalida(f"'{self.valor}' no es un email valido")
        object.__setattr__(self, "valor", limpio)

    def __str__(self) -> str:
        return self.valor


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
