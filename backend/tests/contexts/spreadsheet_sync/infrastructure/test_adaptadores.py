"""Los adaptadores de `spreadsheet_sync`: lo que prometen antes de tocar la red.

Dos afirmaciones, ninguna asíncrona, y las dos sobre configuración más que sobre
comportamiento — por eso viven acá y no junto a los casos de uso.
"""

from __future__ import annotations

import pytest
from cheatsheet.contexts.spreadsheet_sync.infrastructure.almacenamiento import (
    AlmacenamientoEnMemoria,
)
from cheatsheet.contexts.spreadsheet_sync.infrastructure.escritura import EscrituraSimulada
from cheatsheet.contexts.spreadsheet_sync.infrastructure.google_sheets import (
    ALCANCE,
    ProveedorDePlanillaSimulado,
)
from cheatsheet.platform.settings import Entorno


def test_el_alcance_pedido_es_por_archivo_y_no_todo_el_drive() -> None:
    """Caso 9 del plan, y RN-01 en una constante.

    `drive.file` da acceso a los archivos que el usuario eligió con el selector de Google.
    La alternativa que ofrece Google, `spreadsheets`, lee **todas** las planillas de la
    cuenta: las del contador, la de sueldos, los extractos del banco. La historia dice
    «sobre el archivo específico seleccionado, no sobre todo el Drive», y la diferencia
    entre las dos constantes es esa frase.
    """
    assert ALCANCE == "https://www.googleapis.com/auth/drive.file"
    assert not ALCANCE.endswith("/spreadsheets")


def test_los_adaptadores_simulados_son_rechazados_en_produccion() -> None:
    """Caso 8 del plan, y la misma regla que ARCA, WhatsApp y MercadoPago.

    Una empresa que cree que su planilla está vinculada cuando nada llegó a Google es una
    empresa cuyo catálogo nunca se va a llenar, y que no va a saber por qué. Con el
    almacenamiento es peor todavía: los archivos se perderían en el próximo reinicio.
    """
    with pytest.raises(RuntimeError):
        ProveedorDePlanillaSimulado(Entorno.PRODUCTION)

    with pytest.raises(RuntimeError):
        AlmacenamientoEnMemoria(Entorno.PRODUCTION)

    # Y el de la escritura de vuelta: una empresa que cree que el panel alimenta su
    # planilla, y la encuentra vacia un mes despues, estuvo llevando dos juegos de libros
    # sin saberlo.
    with pytest.raises(RuntimeError):
        EscrituraSimulada(Entorno.PRODUCTION)
