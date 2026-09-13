"""`Notificacion` — what the panel tells a person needs their attention (HU-E11-03).

The DER gives it a table with `categoria`, `severidad`, `cuerpo`, `leida` and a nullable
`plantilla_id`. Three things follow from the story and are enforced here:

- **A notification is addressed to a person, not to a company.** RN-02 makes what each user
  receives depend on their own subscription preferences (HU-E1-07), so a row without a
  recipient would be a row nobody is responsible for reading.

- **`leida` is a one-way door.** `marcar_leida` is idempotent and there is no `marcar_no_leida`:
  «lo vi» es un hecho, y un botón que lo deshace convierte el estado de lectura en una
  preferencia de interfaz — que es exactamente lo que deja de servir para saber si alguien se
  enteró de que la sincronización viene fallando hace tres días.

- **La severidad la decide quien notifica, no la pantalla.** RN-04 pide destacar las altas, y
  eso es presentación; pero *cuál* es alta es del dominio, porque la misma categoría puede ser
  rutina o urgencia según lo que pasó.

Nada acá se borra. Una notificación leída queda: es la evidencia de que el sistema avisó.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida

#: HU-E11-03, para el estado vacío de PAN-CFG-NOT.
MENSAJE_SIN_NOTIFICACIONES = "No tenés notificaciones."

LARGO_MAXIMO_DEL_CUERPO = 500


class Severidad(StrEnum):
    """Cuánto importa. El DER declara `severidad varchar` y no enumera los valores, así que
    el catálogo se define acá — cerrado, por lo mismo que `Modulo`: un filtro sobre texto
    libre se pierde en silencio las filas que alguien escribió distinto.

    Tres y no cinco: la pantalla sólo distingue «esto hay que mirarlo ahora» de «esto es
    información», y un catálogo con matices que nadie usa termina con todo en el del medio.
    """

    ALTA = "ALTA"
    MEDIA = "MEDIA"
    BAJA = "BAJA"

    @property
    def se_destaca(self) -> bool:
        """RN-04: «las notificaciones de severidad alta se destacan visualmente»."""
        return self is Severidad.ALTA


@dataclass(slots=True)
class Notificacion:
    """Un aviso dirigido a una persona.

    `categoria` es una `CategoriaDeNotificacion` de `identity` **como texto**: es el mismo
    catálogo con el que el usuario configuró sus suscripciones (HU-E1-07), y este contexto no
    puede importar el `domain/` de aquel (regla R3). Lo que viaja es el valor, que es
    justamente lo que la preferencia guarda.
    """

    id: UUID
    empresa_id: EmpresaId
    destinatario_id: UsuarioId
    categoria: str
    severidad: Severidad
    cuerpo: str
    #: La plantilla que la generó, si salió de una. `None` cuando el texto lo escribió el
    #: sistema en el momento — que es el caso de todo lo que este épico produce.
    plantilla_id: UUID | None = None
    leida: bool = False
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        limpio = self.cuerpo.strip()
        if not limpio:
            raise EntradaInvalida("Una notificación necesita un cuerpo")
        if len(limpio) > LARGO_MAXIMO_DEL_CUERPO:
            raise EntradaInvalida(
                f"El cuerpo de la notificación excede {LARGO_MAXIMO_DEL_CUERPO} caracteres"
            )
        self.cuerpo = limpio
        if not self.categoria.strip():
            raise EntradaInvalida("Una notificación necesita una categoría")

    @property
    def se_destaca(self) -> bool:
        """Alta **y sin leer**. Una alta ya leída dejó de pedir atención, y seguir
        destacándola es cómo una pantalla enseña a ignorar lo que destaca."""
        return self.severidad.se_destaca and not self.leida

    def marcar_leida(self) -> None:
        """RN-03. Idempotente a propósito: dos pestañas abiertas no son un error."""
        self.leida = True


__all__ = [
    "LARGO_MAXIMO_DEL_CUERPO",
    "MENSAJE_SIN_NOTIFICACIONES",
    "Notificacion",
    "Severidad",
]
