"""Corregir una fila con error: lo que el agregado garantiza.

Los contadores los mueve el dominio y nadie más (`corregir_fila`), por la misma razón que
`cerrar` no recibe el estado: un llamador que pudiera escribir `filas_error` a mano es un
llamador que puede hacer que la pantalla mienta.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cheatsheet.contexts.spreadsheet_sync.domain.procesamiento import (
    ErrorDeFila,
    EstadoProcesamiento,
    ProcesamientoDePlanilla,
)
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

AHORA = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
CORREGIDA = datetime(2026, 10, 7, 9, 30, tzinfo=UTC)


def _con_errores(*filas_con_error: int, filas_ok: int = 3) -> ProcesamientoDePlanilla:
    procesamiento = ProcesamientoDePlanilla(
        id=uuid4(),
        empresa_id=EmpresaId(uuid4()),
        vinculo_id=uuid4(),
        mapeo_id=uuid4(),
        created_at=AHORA,
    )
    for _ in range(filas_ok):
        procesamiento.contar_fila_ok()
    for numero in filas_con_error:
        procesamiento.registrar_error(
            error=ErrorDeFila(id=uuid4(), numero_fila=numero, motivo="CUIT invalido")
        )
    procesamiento.cerrar(duracion_ms=10, ahora=AHORA)
    return procesamiento


def test_corregir_una_fila_mueve_los_contadores_y_no_toca_el_total() -> None:
    procesamiento = _con_errores(5, 6, 7)

    procesamiento.corregir_fila(numero_fila=6, ahora=CORREGIDA)

    assert procesamiento.filas_error == 2
    assert procesamiento.filas_ok == 4
    # Es la misma fila: pasó de un lado al otro, no se agregó una.
    assert procesamiento.filas_totales == 6


def test_el_error_se_conserva_como_historia_y_deja_de_ser_pendiente() -> None:
    procesamiento = _con_errores(5, 6)

    procesamiento.corregir_fila(numero_fila=5, ahora=CORREGIDA)

    # No se borra: un procesamiento es el registro de un import.
    assert [e.numero_fila for e in procesamiento.errores] == [5, 6]
    corregido = procesamiento.errores[0]
    assert corregido.corregida_en == CORREGIDA
    assert corregido.pendiente is False
    assert [e.numero_fila for e in procesamiento.errores_pendientes] == [6]


def test_corregir_la_ultima_fila_deja_la_carga_completada() -> None:
    procesamiento = _con_errores(5)
    assert procesamiento.estado.value == "CON_ERRORES"

    procesamiento.corregir_fila(numero_fila=5, ahora=CORREGIDA)

    assert procesamiento.filas_error == 0
    assert procesamiento.estado is EstadoProcesamiento.COMPLETADO


def test_mientras_queden_errores_la_carga_sigue_con_errores() -> None:
    procesamiento = _con_errores(5, 6)

    procesamiento.corregir_fila(numero_fila=5, ahora=CORREGIDA)

    assert procesamiento.estado is EstadoProcesamiento.CON_ERRORES


def test_una_fila_no_se_corrige_dos_veces() -> None:
    """Corregirla de nuevo la importaría dos veces."""
    procesamiento = _con_errores(5, 6)
    procesamiento.corregir_fila(numero_fila=5, ahora=CORREGIDA)

    with pytest.raises(EntradaInvalida, match="no tiene un error pendiente"):
        procesamiento.corregir_fila(numero_fila=5, ahora=CORREGIDA)

    assert procesamiento.filas_error == 1
    assert procesamiento.filas_ok == 4


def test_una_fila_que_nunca_fallo_no_se_corrige() -> None:
    procesamiento = _con_errores(5)

    with pytest.raises(EntradaInvalida, match="no tiene un error pendiente"):
        procesamiento.corregir_fila(numero_fila=2, ahora=CORREGIDA)

    assert procesamiento.filas_error == 1


def test_una_carga_fallida_no_se_corrige() -> None:
    """Nunca ingirió nada y su único error es el archivo, no una fila."""
    procesamiento = ProcesamientoDePlanilla(
        id=uuid4(),
        empresa_id=EmpresaId(uuid4()),
        vinculo_id=uuid4(),
        mapeo_id=uuid4(),
        created_at=AHORA,
    )
    procesamiento.abortar(motivo="El archivo no se puede leer", duracion_ms=5, ahora=AHORA)

    with pytest.raises(InvarianteViolada, match="con errores"):
        procesamiento.corregir_fila(numero_fila=1, ahora=CORREGIDA)


def test_reprocesar_no_vuelve_a_leer_lo_corregido() -> None:
    """Sin esto, reprocesar volvería a leer una fila que ya está en el catálogo."""
    procesamiento = _con_errores(5, 6, 7)
    assert procesamiento.filas_a_reprocesar == (5, 6, 7)

    procesamiento.corregir_fila(numero_fila=6, ahora=CORREGIDA)

    assert procesamiento.filas_a_reprocesar == (5, 7)
