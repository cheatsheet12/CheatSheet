"""Qué fallas de la base son transitorias (se reintentan) y cuáles son del estado (se descartan) (U7, H4)."""

from __future__ import annotations

import pytest
from cheatsheet.api.entregas import es_falla_transitoria
from sqlalchemy.exc import (
    DataError,
    DBAPIError,
    IntegrityError,
    InterfaceError,
    OperationalError,
    ProgrammingError,
)
from sqlalchemy.exc import TimeoutError as TiempoAgotadoDelPool


class _ErrorDeLaBase(Exception):
    def __init__(self, sqlstate: str) -> None:
        super().__init__("error de la base")
        self.sqlstate = sqlstate


@pytest.mark.parametrize(
    "error",
    [
        OperationalError("SELECT", {}, ConnectionResetError("caida")),
        InterfaceError("SELECT", {}, ConnectionResetError("caida")),
        TiempoAgotadoDelPool("el pool no dio una conexion"),
        ConnectionRefusedError("rechazada"),
        TimeoutError("lenta"),
        DBAPIError("SELECT", {}, _ErrorDeLaBase("40P01")),  # deadlock
        DBAPIError("SELECT", {}, _ErrorDeLaBase("57P01")),  # la base se está apagando
    ],
)
def test_las_fallas_de_conexion_tiempo_y_deadlock_son_transitorias(error: Exception) -> None:
    assert es_falla_transitoria(error) is True


@pytest.mark.parametrize(
    "error",
    [
        IntegrityError("INSERT", {}, _ErrorDeLaBase("23505")),
        DataError("INSERT", {}, _ErrorDeLaBase("22001")),
        ProgrammingError("SELECT", {}, _ErrorDeLaBase("42P01")),
        DBAPIError("SELECT", {}, _ErrorDeLaBase("XX000")),
        RuntimeError("nuestro"),
        ValueError("nuestro"),
    ],
)
def test_un_error_del_estado_o_de_nuestro_codigo_no_es_transitorio(error: Exception) -> None:
    assert es_falla_transitoria(error) is False
