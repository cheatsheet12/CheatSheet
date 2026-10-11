"""`ConfirmacionDeLaUnidad`: confirma y vuelve a declarar la empresa (U7, D-U7-3, H1).

Sin Docker: el motor real lo cubre `test_barrido_de_recordatorios_postgres.py` en la CI. Acá se
fija el orden de las llamadas y que un commit rechazado no deje la sesión inservible.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from cheatsheet.platform.database import GUC_EMPRESA
from cheatsheet.platform.transaccion import ConfirmacionDeLaUnidad
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.transaccion import DespachoNoPersistido
from sqlalchemy.exc import OperationalError

pytestmark = pytest.mark.asyncio


class _Sesion:
    def __init__(self, *, commit_falla: bool = False) -> None:
        self.llamadas: list[str] = []
        self.parametros: list[dict[str, Any]] = []
        self._commit_falla = commit_falla

    async def commit(self) -> None:
        self.llamadas.append("commit")
        if self._commit_falla:
            raise OperationalError("COMMIT", {}, Exception("conexión caída de Ana Diaz"))

    async def rollback(self) -> None:
        self.llamadas.append("rollback")

    async def execute(self, sentencia: object, parametros: dict[str, Any]) -> None:
        del sentencia
        self.llamadas.append("set_config")
        self.parametros.append(parametros)


async def test_confirma_y_vuelve_a_declarar_la_empresa_de_la_transaccion_nueva() -> None:
    empresa = EmpresaId(uuid4())
    sesion = _Sesion()

    await ConfirmacionDeLaUnidad(sesion, empresa).confirmar()  # type: ignore[arg-type]

    assert sesion.llamadas == ["commit", "set_config"]
    assert sesion.parametros == [{"clave": GUC_EMPRESA, "valor": str(empresa)}]


async def test_un_commit_rechazado_levanta_despacho_no_persistido_y_deja_la_sesion_usable() -> None:
    empresa = EmpresaId(uuid4())
    sesion = _Sesion(commit_falla=True)

    with pytest.raises(DespachoNoPersistido) as error:
        await ConfirmacionDeLaUnidad(sesion, empresa).confirmar()  # type: ignore[arg-type]

    assert sesion.llamadas == ["commit", "rollback", "set_config"]
    # El texto de la excepción original puede traer datos de la fila: no viaja.
    assert "Ana" not in str(error.value)
