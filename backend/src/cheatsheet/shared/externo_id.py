"""El id con el que Meta identifica un mensaje (`wamid`) y el largo de la columna que lo guarda.

Una sola definición para los dos contextos que lo guardan (`mensaje.externo_id` y
`recordatorio.externo_id`) y para el parser de los callbacks: si la columna cambia de largo, cambia
acá y en ningún otro lado.

**Un id nunca se corta**: uno truncado coincidiría con el de otro mensaje y un callback le
cambiaría el estado a quien no corresponde. Lo que no entra se guarda como «sin id»: el mensaje
salió igual, y lo único que se pierde es el estado de entrega.
"""

from __future__ import annotations

#: El largo de las columnas `mensaje.externo_id` y `recordatorio.externo_id`.
LARGO_MAXIMO_EXTERNO_ID = 160


def externo_id_o_ninguno(externo_id: str | None) -> str | None:
    """El id tal cual si es utilizable; `None` si falta, está vacío o no entra en la columna."""
    if not externo_id or len(externo_id) > LARGO_MAXIMO_EXTERNO_ID:
        return None
    return externo_id


__all__ = ["LARGO_MAXIMO_EXTERNO_ID", "externo_id_o_ninguno"]
