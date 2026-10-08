"""La forma JSON del horario de atención, tal como vive en `regla_de_negocio.configuracion`.

```
{"version": 1, "politica": "AGENTE_RESPONDE" | "MENSAJE_FIJO",
 "dias": [{"dia": 0..6, "franjas": [{"desde": "HH:MM", "hasta": "HH:MM"}, ...]}],
 "fechas_cerradas": ["AAAA-MM-DD", ...]}
```

Se escriben sólo los días con franjas y `fechas_cerradas` siempre (ordenada). Al leer,
`fechas_cerradas` puede faltar (= `[]`: cubre el JSON escrito a mano) y **cualquier otra
`version` se rechaza**. Leer una fila mal formada falla al construir (D24).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from cheatsheet.contexts.business_config.domain.horario_de_atencion import (
    ConfiguracionDeAtencion,
    FranjaDeAtencion,
    PoliticaFueraDeHorario,
)
from cheatsheet.shared.errors import EntradaInvalida

VERSION = 1

MENSAJE_FORMATO_DE_FECHA = "La fecha debe tener el formato AAAA-MM-DD."
MENSAJE_VERSION_DESCONOCIDA = "La versión de la configuración del horario no es compatible."
MENSAJE_POLITICA_INVALIDA = "La política de fuera de horario no es válida."
MENSAJE_FORMA_INVALIDA = "El horario de atención no tiene la forma esperada."

_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def como_json(configuracion: ConfiguracionDeAtencion) -> dict[str, Any]:
    return {
        "version": VERSION,
        "politica": configuracion.politica.value,
        "dias": [
            {
                "dia": dia,
                "franjas": [
                    {"desde": desde, "hasta": hasta}
                    for desde, hasta in (franja.como_textos() for franja in franjas)
                ],
            }
            for dia, franjas in sorted(configuracion.dias.items())
        ],
        "fechas_cerradas": [fecha.isoformat() for fecha in sorted(configuracion.fechas_cerradas)],
    }


def desde_json(crudo: dict[str, Any]) -> ConfiguracionDeAtencion:
    """Reconstruye desde la columna. **Falla si la fila está mal formada.**"""
    if crudo.get("version") != VERSION:
        raise EntradaInvalida(MENSAJE_VERSION_DESCONOCIDA)
    return ConfiguracionDeAtencion(
        dias=_dias(crudo.get("dias")),
        fechas_cerradas=_fechas(crudo.get("fechas_cerradas", [])),
        politica=_politica(crudo.get("politica")),
    )


def _politica(crudo: object) -> PoliticaFueraDeHorario:
    try:
        return PoliticaFueraDeHorario(str(crudo))
    except ValueError as exc:
        raise EntradaInvalida(MENSAJE_POLITICA_INVALIDA) from exc


def _dias(crudo: object) -> dict[int, tuple[FranjaDeAtencion, ...]]:
    if not isinstance(crudo, list):
        raise EntradaInvalida(MENSAJE_FORMA_INVALIDA)
    dias: dict[int, tuple[FranjaDeAtencion, ...]] = {}
    for entrada in crudo:
        if not isinstance(entrada, dict):
            raise EntradaInvalida(MENSAJE_FORMA_INVALIDA)
        dia = entrada.get("dia")
        if isinstance(dia, bool) or not isinstance(dia, int):
            raise EntradaInvalida(MENSAJE_FORMA_INVALIDA)
        if dia in dias:
            raise EntradaInvalida(f"El día {dia} está repetido.")
        dias[dia] = _franjas(entrada.get("franjas"))
    return dias


def _franjas(crudo: object) -> tuple[FranjaDeAtencion, ...]:
    if not isinstance(crudo, list):
        raise EntradaInvalida(MENSAJE_FORMA_INVALIDA)
    franjas: list[FranjaDeAtencion] = []
    for franja in crudo:
        if not isinstance(franja, dict):
            raise EntradaInvalida(MENSAJE_FORMA_INVALIDA)
        desde, hasta = str(franja.get("desde")), str(franja.get("hasta"))
        franjas.append(FranjaDeAtencion.desde_textos(desde, hasta))
    return tuple(franjas)


def _fechas(crudo: object) -> frozenset[date]:
    if not isinstance(crudo, list):
        raise EntradaInvalida(MENSAJE_FORMA_INVALIDA)
    fechas: set[date] = set()
    for texto in crudo:
        fecha = _fecha(texto)
        if fecha in fechas:
            raise EntradaInvalida(f"La fecha {fecha.isoformat()} está repetida.")
        fechas.add(fecha)
    return frozenset(fechas)


def _fecha(texto: object) -> date:
    if not isinstance(texto, str) or _FECHA.match(texto) is None:
        raise EntradaInvalida(MENSAJE_FORMATO_DE_FECHA)
    try:
        return date.fromisoformat(texto)
    except ValueError as exc:
        raise EntradaInvalida(MENSAJE_FORMATO_DE_FECHA) from exc


__all__ = [
    "MENSAJE_FORMATO_DE_FECHA",
    "MENSAJE_FORMA_INVALIDA",
    "MENSAJE_POLITICA_INVALIDA",
    "MENSAJE_VERSION_DESCONOCIDA",
    "VERSION",
    "como_json",
    "desde_json",
]
