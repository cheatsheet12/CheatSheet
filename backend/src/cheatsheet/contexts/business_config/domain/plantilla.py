"""`PlantillaDeNotificacion` — el texto que el sistema le manda a alguien (HU-E11-02).

Tres reglas viven acá, y las tres salen de la historia:

1. **Las variables se validan contra un catálogo por código** (RN-02 y el tercer criterio).
   Cada plantilla sabe qué variables admite: `{{nombre}}` en un recordatorio de turno es
   legítimo y en uno de cobro puede no serlo. Aceptar cualquier variable haría que el mensaje
   saliera con un `{{fehca_del_turno}}` literal al cliente — que es exactamente lo que la
   validación de la historia evita.

2. **Una plantilla de WhatsApp no aprobada no se puede usar por ese canal** (RN-03, RN-04).
   Meta aprueba las plantillas de mensajes iniciados por la empresa, y mandar una sin aprobar
   no falla en silencio: falla con el mensaje sin entregar y la cuenta un poco más cerca de una
   sanción.

3. **El reemplazo es literal y no evalúa nada.** `{{variable}}` se cambia por su valor y punto.
   No hay condicionales, ni bucles, ni expresiones: un motor de plantillas dentro de un texto
   que un administrador edita es una superficie de ejecución que este sistema no necesita.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from cheatsheet.contexts.business_config.domain.regla import CanalNotificacion
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida

#: HU-E11-02, tercer criterio, palabra por palabra.
MENSAJE_VARIABLE_INVALIDA = "La variable indicada no es válida para esta plantilla."
MENSAJE_SIN_APROBAR = (
    "La plantilla no está aprobada por Meta y no puede usarse para el canal de WhatsApp."
)

#: `{{nombre_de_variable}}`. Dos llaves y un identificador: nada que se pueda confundir con
#: código, y nada que un texto normal escriba por accidente.
PATRON_DE_VARIABLE = re.compile(r"\{\{([a-z_][a-z0-9_]*)\}\}")


class EstadoDeAprobacion(StrEnum):
    """El `estado_aprobacion_meta` del DER, que ahí es un `varchar` libre.

    Enum acá porque **gobierna una decisión** —RN-04 impide usar la no aprobada— y una decisión
    que depende de comparar contra cadenas sueltas es una decisión que un día compara contra la
    cadena mal escrita.

    `NO_APLICA` es el caso de los canales que no piden aprobación: email y panel. No es un
    estado de Meta, es la ausencia de Meta.
    """

    NO_APLICA = "NO_APLICA"
    PENDIENTE = "PENDIENTE"
    APROBADA = "APROBADA"
    RECHAZADA = "RECHAZADA"


#: Qué variables admite cada código de plantilla.
#:
#: Una tabla y no un campo por plantilla: las variables las decide **quien manda el mensaje**,
#: no quien lo redacta. Un administrador no puede inventar `{{saldo}}` en un recordatorio de
#: turno porque del otro lado nadie se lo va a pasar, y el mensaje saldría con el literal.
VARIABLES_POR_CODIGO: dict[str, frozenset[str]] = {
    "turno_confirmado": frozenset({"nombre", "servicio", "recurso", "fecha", "hora"}),
    "turno_cancelado": frozenset({"nombre", "servicio", "fecha", "hora"}),
    "turno_reprogramado": frozenset(
        {"nombre", "servicio", "fecha", "hora", "fecha_anterior", "hora_anterior"}
    ),
    "recordatorio_de_turno": frozenset({"nombre", "servicio", "fecha", "hora"}),
    "recordatorio_de_cobro": frozenset({"nombre", "monto", "concepto", "link", "vencimiento"}),
    "cobro_generado": frozenset({"nombre", "monto", "concepto", "link"}),
}


def variables_de(cuerpo: str) -> frozenset[str]:
    """Las variables que un texto usa. Sin evaluar nada — es una expresión regular."""
    return frozenset(PATRON_DE_VARIABLE.findall(cuerpo))


@dataclass(slots=True)
class PlantillaDeNotificacion:
    """Un texto parametrizado, con su canal, su idioma y su estado ante Meta."""

    id: UUID
    empresa_id: EmpresaId
    codigo: str
    canal: CanalNotificacion
    idioma: str
    cuerpo: str
    estado_aprobacion: EstadoDeAprobacion = EstadoDeAprobacion.NO_APLICA
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.codigo.strip() or not self.cuerpo.strip():
            raise EntradaInvalida("Una plantilla necesita código y cuerpo")
        self._exigir_variables_validas(self.cuerpo)

    @property
    def variables_admitidas(self) -> frozenset[str]:
        """Las que su código admite. Un código desconocido no admite ninguna.

        Deliberado: una plantilla con un código que el sistema no manda nunca es una plantilla
        que nadie va a usar, y dejarle poner variables libres sería prometerle a alguien que
        va a funcionar.
        """
        return VARIABLES_POR_CODIGO.get(self.codigo, frozenset())

    def editar(self, cuerpo: str, momento: datetime) -> None:
        """Cambia el texto, validando las variables (RN-02).

        **No toca el estado de aprobación**, y eso es a propósito: editar el cuerpo de una
        plantilla aprobada la invalida ante Meta en la práctica, pero quien lo decide es Meta y
        no nosotros. Ponerla en `PENDIENTE` acá sería inventar una respuesta del proveedor.
        Está anotado en los pendientes del épico.
        """
        self._exigir_variables_validas(cuerpo)
        self.cuerpo = cuerpo
        self.updated_at = momento

    @property
    def puede_usarse(self) -> bool:
        """RN-04: una plantilla no aprobada no sirve para el canal que exige aprobación."""
        if self.canal is not CanalNotificacion.WHATSAPP:
            return True
        return self.estado_aprobacion is EstadoDeAprobacion.APROBADA

    def resolver(self, variables: dict[str, str]) -> str:
        """El cuerpo con las variables reemplazadas.

        Una variable que la plantilla usa y el llamador no pasó queda **como está**, con sus
        llaves. Es feo a propósito: un valor vacío escondería el error y el cliente recibiría
        «tu turno del  a las », mientras que el literal se ve en el primer envío de prueba.
        """
        if not self.puede_usarse:
            raise EntradaInvalida(MENSAJE_SIN_APROBAR)

        def cambiar(coincidencia: re.Match[str]) -> str:
            return variables.get(coincidencia.group(1), coincidencia.group(0))

        return PATRON_DE_VARIABLE.sub(cambiar, self.cuerpo)

    def _exigir_variables_validas(self, cuerpo: str) -> None:
        desconocidas = variables_de(cuerpo) - self.variables_admitidas
        if desconocidas:
            # La frase de la historia, letra por letra. El nombre de la variable no se
            # concatena: el criterio de aceptación fija el mensaje exacto.
            raise EntradaInvalida(MENSAJE_VARIABLE_INVALIDA)


__all__ = [
    "MENSAJE_SIN_APROBAR",
    "MENSAJE_VARIABLE_INVALIDA",
    "VARIABLES_POR_CODIGO",
    "EstadoDeAprobacion",
    "PlantillaDeNotificacion",
    "variables_de",
]
