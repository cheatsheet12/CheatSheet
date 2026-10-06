"""La nota de crédito contra el motor (HU-E5-04).

Tres cosas que sólo existen en PostgreSQL:

1. **La numeración de la nota es su propia serie.** ARCA cuenta por `(punto, tipo)`, así que
   la nota de crédito A número 1 convive con la factura A número 1 en el mismo punto. Si el
   índice estuviera mal, esto se caería — y estaría bien que se cayera, porque lo contrario
   es un comprobante que ARCA rechaza.
2. **El `CHECK` de `comprobante_origen_id`.** Sólo una nota de crédito lo lleva, y eso vive
   en el esquema porque es un hecho que un bug futuro podría romper sin que nadie lo note.
3. **`notas_de` contra el aislamiento por empresa.** El listado de anulaciones de un
   comprobante es una consulta por FK, y bajo RLS tiene que seguir sin ver nada de nadie más.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from cheatsheet.contexts.billing.application.notas_de_credito import EstadoDeAnulacion
from cheatsheet.contexts.billing.domain.comprobante import (
    CAE,
    AlicuotaIVA,
    Comprobante,
    EstadoComprobante,
    ItemDeComprobante,
    Receptor,
    nota_de_credito_para,
)
from cheatsheet.contexts.billing.domain.punto_de_venta import PuntoDeVenta, TipoComprobante
from cheatsheet.contexts.billing.infrastructure.repositories import (
    RepositorioPuntoDeVentaPostgres,
)
from cheatsheet.contexts.billing.infrastructure.repositorio_comprobante import (
    RepositorioComprobantePostgres,
)
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.fiscal import CondicionIVA
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
RI = CondicionIVA.RESPONSABLE_INSCRIPTO
UN_CAE = CAE(codigo="75123456789012", vence_el=date(2026, 9, 17))

CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")
CREAR_CLIENTE = text(
    "INSERT INTO cliente (id, empresa_id, nombre, origen, activo, created_at, updated_at) "
    "VALUES (:id, :empresa_id, 'Acme SA', 'PANEL', true, :ahora, :ahora)"
)


async def _empresa(engine_dueno: AsyncEngine) -> EmpresaId:
    empresa_id = EmpresaId(uuid.uuid4())
    async with engine_dueno.begin() as conexion:
        await conexion.execute(CREAR_EMPRESA, {"id": empresa_id})
    return empresa_id


async def _cliente(engine_dueno: AsyncEngine, empresa_id: EmpresaId) -> uuid.UUID:
    cliente_id = uuid.uuid4()
    async with engine_dueno.begin() as conexion:
        await conexion.execute(
            CREAR_CLIENTE, {"id": cliente_id, "empresa_id": empresa_id, "ahora": AHORA}
        )
    return cliente_id


async def _punto(sesiones: async_sessionmaker[AsyncSession], empresa_id: EmpresaId) -> PuntoDeVenta:
    punto = PuntoDeVenta(id=uuid.uuid4(), empresa_id=empresa_id, numero=1, created_at=AHORA)
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioPuntoDeVentaPostgres(sesion).agregar(punto)
    return punto


def _item(precio: str = "1000.00", cantidad: str = "2") -> ItemDeComprobante:
    return ItemDeComprobante(
        id=uuid.uuid4(),
        descripcion="Corte de pelo",
        cantidad=Decimal(cantidad),
        precio_unitario=Decimal(precio),
        alicuota_iva=AlicuotaIVA.GENERAL,
    )


def _original(
    empresa_id: EmpresaId, cliente_id: uuid.UUID, punto: PuntoDeVenta, numero: int = 1
) -> Comprobante:
    """Total de $2420,00."""
    comprobante = Comprobante(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        cliente_id=cliente_id,
        punto_de_venta_id=punto.id,
        tipo=TipoComprobante.FACTURA_A,
        receptor=Receptor(nombre="Acme SA", cuit="30712345671", condicion_iva=RI),
        emisor_condicion_iva=RI,
        created_at=AHORA,
    )
    comprobante.agregar_item(_item())
    comprobante.validar()
    comprobante.enviar_a_arca(numero, AHORA)
    comprobante.autorizar(UN_CAE)
    return comprobante


def _nota(original: Comprobante, *, numero: int, precio: str, cantidad: str) -> Comprobante:
    nota = nota_de_credito_para(
        original,
        nota_id=uuid.uuid4(),
        items=[_item(precio=precio, cantidad=cantidad)],
        ahora=AHORA,
    )
    nota.validar()
    nota.enviar_a_arca(numero, AHORA)
    nota.autorizar(UN_CAE)
    return nota


async def _guardar(
    sesiones: async_sessionmaker[AsyncSession], empresa_id: EmpresaId, *comprobantes: Comprobante
) -> None:
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repo = RepositorioComprobantePostgres(sesion)
        for comprobante in comprobantes:
            await repo.agregar(comprobante)


async def test_la_nota_lleva_su_propia_serie_en_el_mismo_punto(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """ARCA cuenta por `(punto, tipo)`: la factura A 1 y la nota A 1 conviven.

    Si el índice único fuera `(punto, numero)`, esto se caería — y sería un comprobante que
    ARCA rechaza por un número que en realidad estaba libre.
    """
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    punto = await _punto(sesiones, empresa_id)
    original = _original(empresa_id, cliente_id, punto)

    await _guardar(
        sesiones,
        empresa_id,
        original,
        _nota(original, numero=1, precio="1000.00", cantidad="2"),
    )

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        notas = await RepositorioComprobantePostgres(sesion).notas_de(original.id)

    assert [nota.numero for nota in notas] == [1]
    assert notas[0].tipo is TipoComprobante.NOTA_CREDITO_A


async def test_dos_notas_del_mismo_tipo_no_pueden_repetir_numero(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    punto = await _punto(sesiones, empresa_id)
    original = _original(empresa_id, cliente_id, punto)
    await _guardar(
        sesiones, empresa_id, original, _nota(original, numero=1, precio="500.00", cantidad="1")
    )

    with pytest.raises(IntegrityError):
        await _guardar(
            sesiones, empresa_id, _nota(original, numero=1, precio="500.00", cantidad="1")
        )


async def test_el_estado_de_anulacion_suma_solo_las_autorizadas(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """**Decisión D19 contra el motor.** Lo anulado se calcula, no se lee de una columna.

    Una nota rechazada no reversó nada: si contara, un error de ARCA dejaría a la empresa
    sin poder anular su propia factura.
    """
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    punto = await _punto(sesiones, empresa_id)
    original = _original(empresa_id, cliente_id, punto)

    autorizada = _nota(original, numero=1, precio="1000.00", cantidad="1")  # $1210,00
    rechazada = nota_de_credito_para(
        original, nota_id=uuid.uuid4(), items=[_item(precio="1000.00", cantidad="1")], ahora=AHORA
    )
    rechazada.validar()
    rechazada.enviar_a_arca(2, AHORA)
    rechazada.rechazar("Error 10016: algo")

    await _guardar(sesiones, empresa_id, original, autorizada, rechazada)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        estado = await EstadoDeAnulacion(RepositorioComprobantePostgres(sesion)).ejecutar(
            original.id
        )

    assert estado.total_original == Decimal("2420.00")
    assert estado.total_anulado == Decimal("1210.00")
    assert estado.disponible == Decimal("1210.00")
    assert estado.es_parcial


async def test_una_anulacion_total_persiste_el_estado_del_original(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """El caché de D19: `ANULADO` viaja a la fila, y `EstadoDeAnulacion` sigue coincidiendo."""
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    punto = await _punto(sesiones, empresa_id)
    original = _original(empresa_id, cliente_id, punto)
    await _guardar(
        sesiones,
        empresa_id,
        original,
        _nota(original, numero=1, precio="1000.00", cantidad="2"),
    )

    original.anular()
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioComprobantePostgres(sesion).guardar(original)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repo = RepositorioComprobantePostgres(sesion)
        leido = await repo.buscar_por_id(original.id)
        estado = await EstadoDeAnulacion(repo).ejecutar(original.id)

    assert leido is not None
    assert leido.estado is EstadoComprobante.ANULADO
    # Y el CAE sigue ahí: anular no borra lo que ARCA autorizó.
    assert leido.cae == UN_CAE
    assert estado.es_total


async def test_una_empresa_no_ve_las_notas_de_otra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """`notas_de` es una consulta por FK, y bajo RLS tiene que seguir sin ver nada ajeno."""
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)
    cliente_a = await _cliente(engine_dueno, empresa_a)
    punto_a = await _punto(sesiones, empresa_a)
    original = _original(empresa_a, cliente_a, punto_a)
    await _guardar(
        sesiones,
        empresa_a,
        original,
        _nota(original, numero=1, precio="500.00", cantidad="1"),
    )

    async with sesion_de_empresa(sesiones, empresa_b) as sesion:
        assert await RepositorioComprobantePostgres(sesion).notas_de(original.id) == []


async def test_una_factura_no_puede_apuntar_a_un_origen(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """El `CHECK` condicional de ADR-010, que reemplaza a una segunda tabla."""
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    punto = await _punto(sesiones, empresa_id)
    original = _original(empresa_id, cliente_id, punto)
    otra = _original(empresa_id, cliente_id, punto, numero=2)
    await _guardar(sesiones, empresa_id, original, otra)

    with pytest.raises(IntegrityError):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await sesion.execute(
                text("UPDATE comprobante SET comprobante_origen_id = :origen WHERE id = :id"),
                {"id": otra.id, "origen": original.id},
            )
