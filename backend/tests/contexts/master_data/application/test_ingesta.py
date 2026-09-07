"""La ingesta desde planilla, y el parseo que decide si una fila entra o falla.

Dos cosas se prueban acá y son las que más plata mueven:

1. **`1.234,50` es mil doscientos treinta y cuatro con cincuenta**, no `1.23450`. Una
   planilla argentina se escribe así, y leerla con la locale C da un precio equivocado por
   tres órdenes de magnitud, en silencio, en todo el catálogo.
2. **Un CUIT repetido actualiza, no rechaza.** La planilla es la fuente de verdad de los
   datos maestros (ADR-006), así que la segunda sincronización de cada empresa fallaría
   entera si esto rechazara.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.master_data.application.ingesta import (
    FilaDeCatalogo,
    IngerirClienteDesdePlanilla,
    IngerirServicioDesdePlanilla,
)
from cheatsheet.contexts.master_data.domain.cliente import Cliente
from cheatsheet.contexts.master_data.domain.servicio import Servicio
from cheatsheet.contexts.master_data.domain.valores import AlicuotaIVA, OrigenDato
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import ErrorDeDominio

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
CUIT_VALIDO = "30712345671"


class ClientesFalsos:
    def __init__(self) -> None:
        self.guardados: dict[UUID, Cliente] = {}

    async def agregar(self, cliente: Cliente) -> None:
        self.guardados[cliente.id] = cliente

    async def guardar(self, cliente: Cliente) -> None:
        self.guardados[cliente.id] = cliente

    async def buscar_por_id(self, cliente_id: UUID) -> Cliente | None:
        return self.guardados.get(cliente_id)

    async def buscar_por_cuit(self, cuit: str) -> Cliente | None:
        return next(
            (c for c in self.guardados.values() if c.cuit is not None and str(c.cuit) == cuit),
            None,
        )


class ServiciosFalsos:
    def __init__(self) -> None:
        self.guardados: dict[UUID, Servicio] = {}

    async def agregar(self, servicio: Servicio) -> None:
        self.guardados[servicio.id] = servicio

    async def guardar(self, servicio: Servicio) -> None:
        self.guardados[servicio.id] = servicio

    async def buscar_por_id(self, servicio_id: UUID) -> Servicio | None:
        return self.guardados.get(servicio_id)


async def _ingerir_cliente(repo: ClientesFalsos, **campos: str) -> None:
    await IngerirClienteDesdePlanilla(repo).ejecutar(  # type: ignore[arg-type]
        empresa_id=EMPRESA, fila=FilaDeCatalogo(**campos), ahora=AHORA
    )


async def _ingerir_servicio(repo: ServiciosFalsos, **campos: str) -> None:
    await IngerirServicioDesdePlanilla(repo).ejecutar(  # type: ignore[arg-type]
        empresa_id=EMPRESA, fila=FilaDeCatalogo(**campos), ahora=AHORA
    )


async def test_un_cliente_ingerido_nace_con_origen_planilla() -> None:
    """HU-E4-01 RN-01, y lo que después impide que el write-back lo devuelva a la hoja."""
    repo = ClientesFalsos()

    await _ingerir_cliente(repo, nombre="Panaderia Rosa", cuit=CUIT_VALIDO)

    cliente = next(iter(repo.guardados.values()))
    assert cliente.origen is OrigenDato.PLANILLA
    assert cliente.presente_en_planilla


async def test_un_cuit_repetido_actualiza_en_vez_de_rechazar() -> None:
    """ADR-006: la planilla manda. Rechazar haría fallar la segunda sincronización entera."""
    repo = ClientesFalsos()

    await _ingerir_cliente(repo, nombre="Panaderia Rosa", cuit=CUIT_VALIDO)
    await _ingerir_cliente(repo, nombre="Panaderia Dona Rosa SRL", cuit=CUIT_VALIDO)

    assert len(repo.guardados) == 1
    assert next(iter(repo.guardados.values())).nombre == "Panaderia Dona Rosa SRL"


async def test_una_fila_sin_nombre_falla_con_un_error_de_dominio() -> None:
    """Es el contrato con el procesamiento: `ErrorDeDominio` se vuelve un `ErrorDeFila`."""
    with pytest.raises(ErrorDeDominio):
        await _ingerir_cliente(ClientesFalsos(), nombre="   ", cuit=CUIT_VALIDO)


async def test_un_cuit_mal_formado_falla_la_fila_y_no_el_procesamiento() -> None:
    with pytest.raises(ErrorDeDominio):
        await _ingerir_cliente(ClientesFalsos(), nombre="Kiosco", cuit="123")


async def test_dos_clientes_sin_cuit_conviven() -> None:
    """Sin CUIT no hay con qué emparejar, y una planilla real tiene muchos así."""
    repo = ClientesFalsos()

    await _ingerir_cliente(repo, nombre="Kiosco de la esquina")
    await _ingerir_cliente(repo, nombre="Kiosco de enfrente")

    assert len(repo.guardados) == 2


@pytest.mark.parametrize(
    ("crudo", "esperado"),
    [
        ("1.234,50", "1234.50"),
        ("1234.50", "1234.50"),
        ("$ 1.234,50", "1234.50"),
        ("990", "990"),
        ("0,50", "0.50"),
    ],
)
async def test_los_precios_se_leen_en_notacion_argentina(crudo: str, esperado: str) -> None:
    """El test que evita un catálogo entero con precios mil veces más chicos."""
    repo = ServiciosFalsos()

    await _ingerir_servicio(repo, nombre="Corte", precio=crudo)

    servicio = next(iter(repo.guardados.values()))
    assert servicio.precio == Decimal(esperado)


@pytest.mark.parametrize(
    ("crudo", "esperado"),
    [
        ("21", AlicuotaIVA.GENERAL),
        ("21%", AlicuotaIVA.GENERAL),
        ("0.21", AlicuotaIVA.GENERAL),
        ("10,5", AlicuotaIVA.REDUCIDA),
        ("0", AlicuotaIVA.CERO),
        ("", AlicuotaIVA.GENERAL),
    ],
)
async def test_la_alicuota_se_lee_como_la_escribe_una_persona(
    crudo: str, esperado: AlicuotaIVA
) -> None:
    """Y sin columna asume 21%, que es la de casi toda venta en Argentina.

    Fallar la fila en su lugar rechazaría un catálogo entero por una columna que la
    empresa nunca tuvo.
    """
    repo = ServiciosFalsos()

    await _ingerir_servicio(repo, nombre="Corte", precio="100", alicuota_iva=crudo)

    assert next(iter(repo.guardados.values())).alicuota_iva is esperado


async def test_una_alicuota_que_no_existe_falla_la_fila() -> None:
    """A diferencia de la condición de IVA, esta no se puede dejar vacía: define el
    impuesto de cada comprobante que se emita después."""
    with pytest.raises(ErrorDeDominio):
        await _ingerir_servicio(ServiciosFalsos(), nombre="Corte", precio="100", alicuota_iva="7")


async def test_un_precio_que_no_es_numero_falla_la_fila() -> None:
    with pytest.raises(ErrorDeDominio):
        await _ingerir_servicio(ServiciosFalsos(), nombre="Corte", precio="consultar")


async def test_un_servicio_sin_precio_falla_la_fila() -> None:
    with pytest.raises(ErrorDeDominio):
        await _ingerir_servicio(ServiciosFalsos(), nombre="Corte")


async def test_una_condicion_de_iva_irreconocible_queda_vacia_y_no_falla() -> None:
    """Es opcional: dejarla vacía es mejor que adivinarla, y no vale perder la fila."""
    repo = ClientesFalsos()

    await _ingerir_cliente(repo, nombre="Panaderia", cuit=CUIT_VALIDO, condicion_iva="lo que sea")

    assert next(iter(repo.guardados.values())).condicion_iva is None
