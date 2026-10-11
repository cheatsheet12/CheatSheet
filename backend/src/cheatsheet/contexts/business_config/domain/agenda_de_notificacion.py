"""La agenda de notificación de una empresa — cuánto antes de un turno se recuerda (HU-E11-01).

Cada recordatorio es una **anticipación en horas** (1 a 168, una semana), y una empresa tiene de
uno a tres. Sin regla configurada rige `AGENDA_POR_DEFECTO`: un recordatorio 24 horas antes.
**Una regla desactivada apaga los recordatorios** en vez de volver al default: desactivar es la
decisión explícita del negocio de no avisar, y cada mensaje de plantilla de Meta tiene costo
(Gate 1 del 08/10). Esa distinción es del caso de uso (`ConsultarAgendaDeNotificacion`); acá sólo
viven los invariantes y la forma JSON de `regla_de_negocio.configuracion`:

```
{"recordatorios": [{"horas_antes": 24}, {"horas_antes": 2}]}
```

Leer una fila mal formada falla al construir (D24), no a la mitad de un barrido.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cheatsheet.shared.errors import EntradaInvalida

MINIMO_DE_HORAS = 1
MAXIMO_DE_HORAS = 168
MAXIMO_DE_RECORDATORIOS = 3

MENSAJE_HORAS_FUERA_DE_RANGO = (
    f"Las horas de anticipación deben estar entre {MINIMO_DE_HORAS} y {MAXIMO_DE_HORAS}."
)
MENSAJE_SIN_RECORDATORIOS = "Indicá al menos un recordatorio."
MENSAJE_DEMASIADOS_RECORDATORIOS = (
    f"Podés configurar hasta {MAXIMO_DE_RECORDATORIOS} recordatorios por turno."
)
MENSAJE_REPETIDOS = "No puede haber dos recordatorios con la misma anticipación."
MENSAJE_FORMA_INVALIDA = "La agenda de notificación no tiene la forma esperada."


@dataclass(frozen=True, slots=True)
class AnticipacionDeRecordatorio:
    """Cuántas horas antes del inicio del turno sale un recordatorio."""

    horas_antes: int

    def __post_init__(self) -> None:
        # `bool` es un `int`: `True` no es una cantidad de horas.
        if not isinstance(self.horas_antes, int) or isinstance(self.horas_antes, bool):
            raise EntradaInvalida(MENSAJE_FORMA_INVALIDA)
        if not MINIMO_DE_HORAS <= self.horas_antes <= MAXIMO_DE_HORAS:
            raise EntradaInvalida(MENSAJE_HORAS_FUERA_DE_RANGO)

    @property
    def minutos(self) -> int:
        return self.horas_antes * 60


@dataclass(frozen=True, slots=True)
class ConfiguracionDeAgenda:
    """De uno a tres recordatorios, sin repetidos, de mayor a menor anticipación."""

    recordatorios: tuple[AnticipacionDeRecordatorio, ...]

    def __post_init__(self) -> None:
        if not self.recordatorios:
            raise EntradaInvalida(MENSAJE_SIN_RECORDATORIOS)
        if len(self.recordatorios) > MAXIMO_DE_RECORDATORIOS:
            raise EntradaInvalida(MENSAJE_DEMASIADOS_RECORDATORIOS)
        if len({uno.horas_antes for uno in self.recordatorios}) != len(self.recordatorios):
            raise EntradaInvalida(MENSAJE_REPETIDOS)
        ordenados = sorted(self.recordatorios, key=lambda uno: uno.horas_antes, reverse=True)
        object.__setattr__(self, "recordatorios", tuple(ordenados))

    @property
    def anticipaciones_min(self) -> tuple[int, ...]:
        return tuple(uno.minutos for uno in self.recordatorios)

    def como_json(self) -> dict[str, Any]:
        return {"recordatorios": [{"horas_antes": uno.horas_antes} for uno in self.recordatorios]}

    @classmethod
    def desde_json(cls, crudo: dict[str, Any]) -> ConfiguracionDeAgenda:
        """Reconstruye desde la columna. **Falla si la fila está mal formada.**"""
        crudos = crudo.get("recordatorios")
        if not isinstance(crudos, list):
            raise EntradaInvalida(MENSAJE_FORMA_INVALIDA)
        recordatorios: list[AnticipacionDeRecordatorio] = []
        for entrada in crudos:
            if not isinstance(entrada, dict) or "horas_antes" not in entrada:
                raise EntradaInvalida(MENSAJE_FORMA_INVALIDA)
            recordatorios.append(AnticipacionDeRecordatorio(entrada["horas_antes"]))
        return cls(tuple(recordatorios))


#: Lo que rige cuando la empresa nunca configuró la agenda.
AGENDA_POR_DEFECTO = ConfiguracionDeAgenda((AnticipacionDeRecordatorio(24),))


__all__ = [
    "AGENDA_POR_DEFECTO",
    "MAXIMO_DE_HORAS",
    "MAXIMO_DE_RECORDATORIOS",
    "MENSAJE_DEMASIADOS_RECORDATORIOS",
    "MENSAJE_FORMA_INVALIDA",
    "MENSAJE_HORAS_FUERA_DE_RANGO",
    "MENSAJE_REPETIDOS",
    "MENSAJE_SIN_RECORDATORIOS",
    "MINIMO_DE_HORAS",
    "AnticipacionDeRecordatorio",
    "ConfiguracionDeAgenda",
]
