"""La ingesta desde planilla y la normalización — HU-E3-03 RN-04, HU-E3-04 RN-04, HU-E3-07.

Archivo nuevo, aparte de `test_ingesta.py`, a propósito: la unidad `tipos-de-comprobante-
por-receptor` también agrega tests ahí, y así las dos ramas se juntan sin conflicto.

Lo que se fija:

- **Lo que entra de la planilla se guarda normalizado**, y la fila de entrada (que es la
  planilla) no se toca.
- **Una diferencia que desaparece al normalizar no es un cambio**: no se guarda, no se mueve
  `actualizado_en`. Se compara normalizado contra normalizado, de los dos lados, porque lo
  almacenado puede ser anterior a la normalización.
- **Por eso un registro del panel que se reingiere igual no vuelve a la hoja propia**: el
  write-back se acota por `actualizado_en`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cheatsheet.contexts.master_data.application.ingesta import (
    FilaDeCatalogo,
    IngerirClienteDesdePlanilla,
    IngerirServicioDesdePlanilla,
    ListarClientesParaEscrituraDeVuelta,
    ResultadoDeIngesta,
    _condicion_iva,
)
from cheatsheet.contexts.master_data.domain.cliente import Cliente
from cheatsheet.contexts.master_data.domain.valores import OrigenDato
from cheatsheet.shared.contacto import Email
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.fiscal import CUIT, CondicionIVA

from tests.contexts.master_data.conftest import (
    CUIT_VALIDO,
    RepositorioClienteEnMemoria,
    RepositorioServicioEnMemoria,
)

pytestmark = pytest.mark.asyncio

ANTES = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())


class ClientesQueCuentan(RepositorioClienteEnMemoria):
    """El doble de siempre, más cuántas veces se guardó: «no se guarda» es el criterio."""

    def __init__(self) -> None:
        super().__init__()
        self.escrituras = 0

    async def guardar(self, cliente: Cliente) -> None:
        self.escrituras += 1
        await super().guardar(cliente)


def _existente(
    repo: RepositorioClienteEnMemoria,
    *,
    nombre: str = "Maria Gomez",
    origen: OrigenDato = OrigenDato.PLANILLA,
    presente: bool = True,
    email: str | None = None,
) -> Cliente:
    """Se arma el agregado a mano: así «almacenado» puede ser anterior a la normalización."""
    cliente = Cliente(
        id=uuid4(),
        empresa_id=EMPRESA,
        nombre=nombre,
        origen=origen,
        creado_en=ANTES,
        actualizado_en=ANTES,
        cuit=CUIT(CUIT_VALIDO),
        contacto_email=Email(email) if email else None,
        presente_en_planilla=presente,
    )
    repo.clientes[cliente.id] = cliente
    return cliente


async def _ingerir(repo: RepositorioClienteEnMemoria, **campos: str) -> ResultadoDeIngesta:
    return await IngerirClienteDesdePlanilla(repo).ejecutar(
        empresa_id=EMPRESA, fila=FilaDeCatalogo(**campos), ahora=AHORA
    )


# --- Lo que entra se guarda normalizado -----------------------------------------------


async def test_la_fila_se_guarda_normalizada_y_la_de_entrada_no_cambia() -> None:
    repo = RepositorioClienteEnMemoria()
    fila = FilaDeCatalogo(nombre="MARIA DE LOS ANGELES perez  ")

    await IngerirClienteDesdePlanilla(repo).ejecutar(empresa_id=EMPRESA, fila=fila, ahora=AHORA)

    assert next(iter(repo.clientes.values())).nombre == "Maria de los Angeles Perez"
    assert fila.nombre == "MARIA DE LOS ANGELES perez  "


async def test_un_servicio_de_planilla_se_guarda_normalizado() -> None:
    repo = RepositorioServicioEnMemoria()

    await IngerirServicioDesdePlanilla(repo).ejecutar(
        empresa_id=EMPRESA, fila=FilaDeCatalogo(nombre="CORTE DE PELO", precio="5000"), ahora=AHORA
    )

    assert next(iter(repo.servicios.values())).nombre == "Corte de pelo"


# --- Sin falsos cambios en la resincronización -----------------------------------------


async def test_una_diferencia_solo_de_mayusculas_no_es_un_cambio() -> None:
    repo = ClientesQueCuentan()
    existente = _existente(repo, email="ana@mail.com")

    resultado = await _ingerir(
        repo, nombre="MARIA GOMEZ", cuit=CUIT_VALIDO, contacto_email="Ana@Mail.COM"
    )

    assert resultado == ResultadoDeIngesta(creado=False, modificado=False)
    assert repo.escrituras == 0
    assert existente.actualizado_en == ANTES
    assert existente.nombre == "Maria Gomez"


async def test_lo_almacenado_sin_normalizar_tampoco_genera_un_cambio() -> None:
    repo = ClientesQueCuentan()
    existente = _existente(repo, nombre="MARIA  GOMEZ")

    resultado = await _ingerir(repo, nombre="Maria Gomez", cuit=CUIT_VALIDO)

    assert resultado.modificado is False
    assert repo.escrituras == 0
    assert existente.actualizado_en == ANTES


async def test_un_cambio_real_guarda_y_mueve_actualizado_en() -> None:
    repo = ClientesQueCuentan()
    existente = _existente(repo)

    resultado = await _ingerir(repo, nombre="Maria Gomez Ruiz", cuit=CUIT_VALIDO)

    assert resultado == ResultadoDeIngesta(creado=False, modificado=True)
    assert repo.escrituras == 1
    assert existente.nombre == "Maria Gomez Ruiz"
    assert existente.actualizado_en == AHORA


async def test_un_telefono_distinto_es_un_cambio_real() -> None:
    repo = ClientesQueCuentan()
    existente = _existente(repo)

    resultado = await _ingerir(
        repo, nombre="Maria Gomez", cuit=CUIT_VALIDO, contacto_whatsapp="5491112345678"
    )

    assert resultado.modificado is True
    assert existente.actualizado_en == AHORA


async def test_volver_a_aparecer_en_la_planilla_se_marca_sin_mover_actualizado_en() -> None:
    repo = ClientesQueCuentan()
    existente = _existente(repo, presente=False)

    resultado = await _ingerir(repo, nombre="MARIA GOMEZ", cuit=CUIT_VALIDO)

    assert resultado.modificado is False
    assert existente.presente_en_planilla is True
    assert existente.actualizado_en == ANTES
    assert repo.escrituras == 1


# --- HU-E3-07: la hoja propia no recibe lo que no cambió ------------------------------------


@pytest.fixture(autouse=True)
def _limite_de_pagina_valido(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hallazgo fuera de alcance (`TODO.md` §20): `LIMITE` vale 500 y `Pagina` acepta hasta
    200, así que el caso de uso real levanta `EntradaInvalida`. Acá se fija el límite que
    `Pagina` admite para poder probar el criterio; el arreglo es de otra unidad."""
    monkeypatch.setattr(ListarClientesParaEscrituraDeVuelta, "LIMITE", 200)


async def test_un_cliente_de_planilla_no_vuelve_a_la_hoja() -> None:
    repo = RepositorioClienteEnMemoria()
    _existente(repo, origen=OrigenDato.PLANILLA)

    registros = await ListarClientesParaEscrituraDeVuelta(repo).ejecutar(empresa_id=EMPRESA)

    assert registros == ()


async def test_un_cliente_del_panel_reingerido_sin_cambios_reales_no_entra_en_la_ventana() -> None:
    repo = RepositorioClienteEnMemoria()
    _existente(repo, origen=OrigenDato.PANEL)

    await _ingerir(repo, nombre="MARIA GOMEZ", cuit=CUIT_VALIDO)

    desde = AHORA - timedelta(days=1)
    registros = await ListarClientesParaEscrituraDeVuelta(repo).ejecutar(
        empresa_id=EMPRESA, desde=desde
    )
    assert registros == ()


# --- La condición de IVA también recibe RN-01 --------------------------------------------


@pytest.mark.parametrize(
    "crudo", ["  responsable   inscripto ", "Responsable\xa0Inscripto", "RESPONSABLE\tINSCRIPTO"]
)
def test_la_condicion_de_iva_se_limpia_antes_de_mapearse(crudo: str) -> None:
    assert _condicion_iva(crudo) is CondicionIVA.RESPONSABLE_INSCRIPTO


def test_una_condicion_desconocida_sigue_quedando_vacia() -> None:
    assert _condicion_iva("no se") is None
    assert _condicion_iva("   ") is None
