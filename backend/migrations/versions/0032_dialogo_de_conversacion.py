"""El diálogo pendiente de una conversación (decisión D99, pendiente #5 del épico 8).

El agente ofrecía horarios y no recordaba cuáles: por eso «el primero» no reservaba nada. Esta
migración le da dónde guardarlo: `conversacion.dialogo`, un `jsonb` **nullable** con lo que el
sistema le ofreció al cliente y espera que conteste —los horarios, los turnos a cancelar, la
pregunta de confirmación— junto con su vencimiento. El formato lo define el repositorio y lleva
una clave `version`; un JSON de otra versión se lee como «sin diálogo».

Se aparta del DER, que no tiene una columna para el estado de un diálogo, y por eso es la decisión
D99 y no un detalle: es 1 a 1 con la conversación, mismo ciclo de vida y misma RLS, así que una
tabla aparte sería un repositorio y una política más para el mismo dato.

- **Sin backfill.** Todas las conversaciones existentes arrancan sin diálogo.
- **Sin política nueva.** La RLS de `conversacion` (0021) acota por `empresa_id` a nivel de fila,
  así que la columna nueva queda cubierta, y el `GRANT` de tabla del rol de la aplicación la
  incluye.
- **Reversible.** `downgrade` borra la columna.

**Número reservado.** Esta unidad nació sobre 0030 mientras `develop` reservaba 0031 para
`tipos-de-comprobante-por-receptor`. Al integrarla, se renumera al siguiente libre y su
`down_revision` se re-apunta a la cabeza de `develop`, para que quede una sola cabeza.

Revision ID: 0032
Revises: 0030
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0032"
# Re-apuntar al integrar en `develop`: ver «Número reservado» en el docstring.
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE conversacion ADD COLUMN dialogo jsonb NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE conversacion DROP COLUMN IF EXISTS dialogo")
