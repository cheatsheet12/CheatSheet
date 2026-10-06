"""Puertos de `payments` para los recordatorios (HS-T3).

Salieron de `ports.py`, que llegó al tope de 400 líneas (`CLAUDE.md` §5): es un bloque cohesivo
que solo usa `recordatorios.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from cheatsheet.contexts.payments.domain.cobro import Cobro
from cheatsheet.contexts.payments.domain.recordatorio import EstadoEntrega
from cheatsheet.shared.empresa import EmpresaId


class PortEnvioDeRecordatorio(Protocol):
    """Por dónde sale un recordatorio (HS-T3 RN-02).

    Devuelve el estado de entrega que el canal informó, para que RN-04 tenga qué registrar.
    """

    async def enviar(
        self, *, empresa_id: EmpresaId, cobro: Cobro, canal: str, paso: int
    ) -> EstadoEntrega: ...


@dataclass(frozen=True, slots=True)
class PasoDeCadena:
    """Un eslabón de la cadena de escalamiento, en el vocabulario de `payments`.

    **`business_config` tiene su propia clase con la misma forma**, y esa duplicación es la
    correcta: un puerto es el contrato del *consumidor*. La regla R3 impide que este contexto
    importe el dominio del otro, y la traducción vive en el ACL de `infrastructure/` -- que es
    exactamente lo que ADR-0003 pide.

    `dias` se cuenta desde el **vencimiento** del cobro, no desde el paso anterior.
    """

    dias: int
    canal: str


class PortCadenaDeEscalamiento(Protocol):
    """Cuál es la cadena de recordatorios de esta empresa (HU-E11-01 RN-02).

    Devuelve los pasos ya ordenados y ya resueltos por prioridad: la resolución de RN-05 es
    cosa de `business_config`, y este contexto recibe la respuesta, no las filas.

    **Nunca devuelve una lista vacía.** Sin regla configurada devuelve el default, porque
    HS-T3 tiene como precondición que exista una cadena y una empresa que nunca entró a
    PAN-CFG-RN no puede quedarse sin recordatorios y sin enterarse.
    """

    async def pasos(self, *, empresa_id: EmpresaId) -> tuple[PasoDeCadena, ...]: ...


__all__ = [
    "PasoDeCadena",
    "PortCadenaDeEscalamiento",
    "PortEnvioDeRecordatorio",
]
