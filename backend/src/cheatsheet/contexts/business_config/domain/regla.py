"""`ReglaDeNegocio` — el comportamiento del sistema, parametrizado por empresa (HU-E11-01).

El DER pone las tres clases de regla en una tabla con `configuracion jsonb`, y este archivo
respeta esa decisión (**D24**). Lo que agrega es que **cada tipo tiene su propia clase de
configuración, que valida al construirse**: nada en el sistema lee `configuracion["dias"]`
directamente, y una regla mal formada falla acá y no a la mitad de un barrido.

Una tabla por tipo habría dado validación en el esquema y costado tres migraciones por cada
tipo nuevo — además de romper la resolución por prioridad de RN-05, que compara reglas de
tipos distintos entre sí.

**Una regla desactivada deja de aplicarse de inmediato** (RN-04) y no toca nada de lo ya
procesado: es un `WHERE activa`, no un borrado. Un recordatorio que ya salió salió bajo la
regla que regía entonces, y eso es correcto.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from cheatsheet.contexts.business_config.domain.agenda_de_notificacion import (
    ConfiguracionDeAgenda,
)
from cheatsheet.contexts.business_config.domain.horario_de_atencion import ConfiguracionDeAtencion
from cheatsheet.contexts.business_config.domain.horario_de_atencion_json import desde_json
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida

#: HU-E11-01, palabra por palabra. Constante porque la historia la escribe y un test la afirma.
MENSAJE_DIAS_INVALIDOS = "Los días de escalamiento deben ser mayores a cero."
MENSAJE_SIN_PASOS = "La regla de escalamiento necesita al menos un paso."

#: Tope de pasos de una cadena de recordatorios. No sale de ninguna historia: sale de que
#: una cadena de veinte mensajes por una deuda es acoso, y de que el sistema no debería
#: permitir configurarlo aunque alguien lo pida.
MAXIMO_DE_PASOS = 6


class TipoRegla(StrEnum):
    """El enum `tipo_regla` del DER.

    Los tres existen desde el principio aunque el épico 6 sólo use el primero, por la misma
    razón que `ServicioDeArca` incluyó `PADRON_A5` antes de tiempo: el valor es parte de una
    clave de almacenamiento, y un catálogo ampliado más tarde por una unidad que no tiene
    otro motivo para tocar este archivo es peor que uno escrito una vez.
    """

    ESCALAMIENTO_DE_COBRO = "ESCALAMIENTO_DE_COBRO"
    POLITICA_DE_TURNO = "POLITICA_DE_TURNO"
    AGENDA_DE_NOTIFICACION = "AGENDA_DE_NOTIFICACION"
    #: Cuándo atiende el negocio y qué hace el agente fuera de horario (HS-T2 RN-04, D100).
    HORARIO_DE_ATENCION = "HORARIO_DE_ATENCION"


class CanalNotificacion(StrEnum):
    """El enum `canal_notificacion` del DER.

    Vive acá porque es `business_config` quien decide por dónde sale un aviso. `payments` lo
    consume a través del servicio de aplicación, nunca importando este módulo (R3).
    """

    WHATSAPP = "WHATSAPP"
    EMAIL = "EMAIL"
    PANEL = "PANEL"


@dataclass(frozen=True, slots=True)
class PasoDeEscalamiento:
    """Un eslabón de la cadena: cuántos días después del vencimiento, y por dónde.

    `dias` se cuenta **desde el vencimiento del cobro**, no desde el paso anterior. Es lo que
    hace que la cadena se pueda leer de un vistazo —«a los 3, a los 7, a los 15»— y lo que
    permite que el barrido de HS-T3 decida el paso que corresponde con una sola comparación.
    """

    dias: int
    canal: CanalNotificacion

    def __post_init__(self) -> None:
        if self.dias <= 0:
            # El texto de la historia, para que llegue a la pantalla.
            raise EntradaInvalida(MENSAJE_DIAS_INVALIDOS)


@dataclass(frozen=True, slots=True)
class ConfiguracionDeEscalamiento:
    """La regla de HU-E11-01 RN-02: cada cuántos días y por qué canal.

    Los pasos se guardan **ordenados por día** y esa normalización es del dominio y no de
    quien la carga: el barrido de HS-T3 recorre la lista de menor a mayor, y una configuración
    escrita al revés en la base haría que la cadena empezara por el último recordatorio.
    """

    pasos: tuple[PasoDeEscalamiento, ...]

    def __post_init__(self) -> None:
        if not self.pasos:
            raise EntradaInvalida(MENSAJE_SIN_PASOS)
        if len(self.pasos) > MAXIMO_DE_PASOS:
            raise EntradaInvalida(
                f"Una cadena de recordatorios no puede tener mas de {MAXIMO_DE_PASOS} pasos"
            )
        ordenados = tuple(sorted(self.pasos, key=lambda paso: paso.dias))
        if len({paso.dias for paso in ordenados}) != len(ordenados):
            # Dos pasos el mismo día son dos mensajes seguidos por la misma deuda.
            raise EntradaInvalida("No puede haber dos pasos de escalamiento el mismo dia")
        object.__setattr__(self, "pasos", ordenados)

    def paso_numero(self, numero: int) -> PasoDeEscalamiento | None:
        """El paso `numero` de la cadena, contando desde 1. `None` cuando se acabó.

        Contar desde 1 y no desde 0 es deliberado: `recordatorio.paso` es una columna que
        alguien va a leer en una consulta, y «paso 0» no significa nada para quien la mire.
        """
        if 1 <= numero <= len(self.pasos):
            return self.pasos[numero - 1]
        return None

    @property
    def cantidad_de_pasos(self) -> int:
        return len(self.pasos)

    def como_json(self) -> dict[str, Any]:
        return {"pasos": [{"dias": paso.dias, "canal": paso.canal.value} for paso in self.pasos]}

    @classmethod
    def desde_json(cls, crudo: dict[str, Any]) -> ConfiguracionDeEscalamiento:
        """Reconstruye desde la columna. **Falla si la fila está mal formada.**

        Es el punto de D24: la validación no está en el esquema, así que tiene que estar
        acá — y tiene que romper al leer, no propagar un `KeyError` a la mitad de un barrido
        que ya mandó tres mensajes.
        """
        crudos = crudo.get("pasos")
        if not isinstance(crudos, list):
            raise EntradaInvalida("La regla de escalamiento no tiene pasos")
        pasos: list[PasoDeEscalamiento] = []
        for paso in crudos:
            if not isinstance(paso, dict):
                raise EntradaInvalida("Un paso de escalamiento no tiene la forma esperada")
            try:
                pasos.append(
                    PasoDeEscalamiento(
                        dias=int(paso["dias"]), canal=CanalNotificacion(paso["canal"])
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise EntradaInvalida("Un paso de escalamiento no tiene la forma esperada") from exc
        return cls(pasos=tuple(pasos))


#: La cadena que rige cuando la empresa no configuró ninguna.
#:
#: **Existe a propósito y no es una comodidad.** HS-T3 tiene como precondición «existe una
#: regla de escalamiento activa», y sin un default eso significa que una empresa que nunca
#: entró a PAN-CFG-RN no recibe ningún recordatorio y no se entera. Tres pasos por WhatsApp
#: es lo que hace un cobrador razonable, y la empresa puede cambiarlo.
ESCALAMIENTO_POR_DEFECTO = ConfiguracionDeEscalamiento(
    pasos=(
        PasoDeEscalamiento(dias=3, canal=CanalNotificacion.WHATSAPP),
        PasoDeEscalamiento(dias=7, canal=CanalNotificacion.WHATSAPP),
        PasoDeEscalamiento(dias=15, canal=CanalNotificacion.WHATSAPP),
    )
)


def _exigir_prioridad_valida(prioridad: int) -> None:
    if prioridad < 0:
        raise EntradaInvalida("La prioridad de una regla no puede ser negativa")


@dataclass(slots=True)
class ReglaDeNegocio:
    """Una regla parametrizable de una empresa.

    `configuracion` viaja como `dict` porque es lo que la columna guarda, y se interpreta con
    la clase que corresponde al tipo. `interpretada_como_escalamiento` es la única lectura
    tipada que el épico 6 necesita; los otros dos tipos suman la suya cuando su épico llegue.
    """

    id: UUID
    empresa_id: EmpresaId
    tipo: TipoRegla
    configuracion: dict[str, Any]
    created_at: datetime
    prioridad: int = 0
    activa: bool = True
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        _exigir_prioridad_valida(self.prioridad)

    def interpretada_como_escalamiento(self) -> ConfiguracionDeEscalamiento:
        """La configuración, tipada. Falla si el tipo no es el que se pide."""
        if self.tipo is not TipoRegla.ESCALAMIENTO_DE_COBRO:
            raise EntradaInvalida(
                f"La regla {self.id} no es de escalamiento de cobro, es {self.tipo.value}"
            )
        return ConfiguracionDeEscalamiento.desde_json(self.configuracion)

    def interpretada_como_atencion(self) -> ConfiguracionDeAtencion:
        """El horario de atención, tipado. Falla si el tipo no es el que se pide."""
        if self.tipo is not TipoRegla.HORARIO_DE_ATENCION:
            raise EntradaInvalida(
                f"La regla {self.id} no es un horario de atención, es {self.tipo.value}"
            )
        return desde_json(self.configuracion)

    def interpretada_como_agenda(self) -> ConfiguracionDeAgenda:
        """La agenda de notificación, tipada. Falla si el tipo no es el que se pide."""
        if self.tipo is not TipoRegla.AGENDA_DE_NOTIFICACION:
            raise EntradaInvalida(
                f"La regla {self.id} no es una agenda de notificación, es {self.tipo.value}"
            )
        return ConfiguracionDeAgenda.desde_json(self.configuracion)

    def cambiar_prioridad(self, prioridad: int) -> None:
        """Reemplaza la prioridad con la misma regla que la construcción (no negativa)."""
        _exigir_prioridad_valida(prioridad)
        self.prioridad = prioridad

    def reconfigurar(self, configuracion: dict[str, Any], ahora: datetime) -> None:
        """Reemplaza la parametrización. La validación es de quien construye la nueva."""
        self.configuracion = configuracion
        self.updated_at = ahora

    def activar(self, ahora: datetime) -> None:
        self.activa = True
        self.updated_at = ahora

    def desactivar(self, ahora: datetime) -> None:
        """RN-04: deja de aplicarse de inmediato y no toca nada de lo ya procesado.

        Es un `WHERE activa` y no un borrado: un recordatorio que ya salió salió bajo la
        regla que regía entonces, y borrarla dejaría la bitácora apuntando a la nada.
        """
        self.activa = False
        self.updated_at = ahora


def resolver(reglas: list[ReglaDeNegocio], tipo: TipoRegla) -> ReglaDeNegocio | None:
    """RN-05 — cuál de varias reglas aplicables gana.

    **Mayor prioridad primero**, y a igualdad la más reciente. El desempate importa: dos
    reglas con la misma prioridad es una configuración que alguien va a armar sin querer, y
    «la que se cargó después» es la interpretación que menos sorprende — es la que la persona
    acaba de escribir.
    """
    candidatas = [regla for regla in reglas if regla.activa and regla.tipo is tipo]
    if not candidatas:
        return None
    return max(candidatas, key=lambda regla: (regla.prioridad, regla.created_at))


@dataclass(frozen=True, slots=True)
class ReglasVigentes:
    """Lo que un consumidor de otro contexto recibe: la respuesta, no las filas.

    `payments` pregunta «cuál es la cadena de recordatorios de esta empresa» y recibe una
    `ConfiguracionDeEscalamiento`, nunca una `ReglaDeNegocio`. La prioridad, el estado activo
    y la fila son cosas de `business_config`.
    """

    escalamiento: ConfiguracionDeEscalamiento = field(default=ESCALAMIENTO_POR_DEFECTO)
    #: `False` cuando se está usando el default. La pantalla lo dice, para que nadie crea que
    #: configuró algo que no configuró.
    configurada: bool = False


__all__ = [
    "ESCALAMIENTO_POR_DEFECTO",
    "MAXIMO_DE_PASOS",
    "MENSAJE_DIAS_INVALIDOS",
    "MENSAJE_SIN_PASOS",
    "CanalNotificacion",
    "ConfiguracionDeEscalamiento",
    "PasoDeEscalamiento",
    "ReglaDeNegocio",
    "ReglasVigentes",
    "TipoRegla",
    "resolver",
]
