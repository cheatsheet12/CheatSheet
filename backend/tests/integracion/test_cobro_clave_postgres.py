"""La clave de idempotencia del pedido contra el motor (ADR-0013, casos 12 a 14).

Lo que no se puede probar con un doble: el **bloqueo consultivo** que serializa dos pedidos
simultáneos, el **índice único parcial** `(empresa_id, clave_idempotencia)` y que RLS cubra la
columna nueva. Necesitan PostgreSQL: se saltean sin base y corren en CI.

Con el transporte ASGI de los tests una excepción del servidor se propaga en vez de volverse un
500, así que los pedidos concurrentes se juntan con `return_exceptions=True` y se afirma que
ninguno falló: si la carrera no ocurriera, el test igual tiene que pasar.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from cheatsheet.contexts.payments.application.errors import PedidoEnCurso
from cheatsheet.contexts.payments.application.generacion_de_cobro import GenerarCobro
from cheatsheet.contexts.payments.domain.cobro import Cobro, LinkDePago
from cheatsheet.contexts.payments.infrastructure.repositories import RepositorioCobroPostgres
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.roles import RolUsuario
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.contexts.payments.application.test_confirmacion import (
    ClientesFalsos,
    PasarelaFalsa,
    PublicadorFalso,
    SaldosFalsos,
)
from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

AHORA = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
USUARIO = UsuarioId(uuid.uuid4())

CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")
CREAR_CLIENTE = text(
    "INSERT INTO cliente (id, empresa_id, nombre, origen, activo, created_at, updated_at) "
    "VALUES (:id, :empresa_id, 'Acme SA', 'PANEL', true, :ahora, :ahora)"
)
CONTAR = text("SELECT count(*) FROM cobro WHERE empresa_id = :empresa_id")


class PasarelaLenta(PasarelaFalsa):
    """MercadoPago demora: avisa que el primer pedido llegó y espera que lo suelten."""

    def __init__(self) -> None:
        super().__init__()
        self.llego = asyncio.Event()
        self.soltar = asyncio.Event()

    async def crear_link(
        self, *, empresa_id: EmpresaId, cobro: Cobro, url_de_retorno: str
    ) -> LinkDePago:
        self.llego.set()
        await self.soltar.wait()
        return await super().crear_link(
            empresa_id=empresa_id, cobro=cobro, url_de_retorno=url_de_retorno
        )


async def _empresa_con_cliente(engine_dueno: AsyncEngine) -> tuple[EmpresaId, uuid.UUID]:
    empresa_id, cliente_id = EmpresaId(uuid.uuid4()), uuid.uuid4()
    async with engine_dueno.begin() as conexion:
        await conexion.execute(CREAR_EMPRESA, {"id": empresa_id})
        await conexion.execute(
            CREAR_CLIENTE, {"id": cliente_id, "empresa_id": empresa_id, "ahora": AHORA}
        )
    return empresa_id, cliente_id


async def _pedir(
    sesiones: async_sessionmaker[AsyncSession],
    pasarela: PasarelaFalsa,
    *,
    empresa_id: EmpresaId,
    cliente_id: uuid.UUID,
    clave: uuid.UUID,
) -> Cobro:
    """Un pedido de punta a punta en su propia transacción, como el router."""
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        return await GenerarCobro(
            cobros=RepositorioCobroPostgres(sesion),
            pasarela=pasarela,
            saldos=SaldosFalsos(cliente=cliente_id),
            clientes=ClientesFalsos(cliente_id),
            publicador=PublicadorFalso(),
            url_de_retorno="https://panel.cheatsheet.ar/cobros",
        ).ejecutar(
            empresa_id=empresa_id,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            clave_idempotencia=clave,
            cliente_id=cliente_id,
            monto=Decimal("1210.00"),
            descripcion="Consulta de octubre",
            ahora=AHORA,
        )


def _cobro_con_clave(empresa_id: EmpresaId, cliente_id: uuid.UUID, clave: uuid.UUID) -> Cobro:
    cobro = Cobro(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        cliente_id=cliente_id,
        monto=Decimal("10.00"),
        descripcion="Duplicado",
        vence_el=AHORA,
        created_at=AHORA,
        updated_at=AHORA,
        clave_idempotencia=clave,
    )
    cobro.asignar_link(LinkDePago(preference_id=f"pref-{cobro.id}", url="https://mp.com/x"), AHORA)
    return cobro


async def test_dos_pedidos_concurrentes_con_la_misma_clave_dejan_un_cobro_y_una_preferencia(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Caso 12. El segundo espera al primero (que demora en MercadoPago) y devuelve su cobro."""
    empresa_id, cliente_id = await _empresa_con_cliente(engine_dueno)
    clave = uuid.uuid4()
    pasarela = PasarelaLenta()

    primero = asyncio.create_task(
        _pedir(sesiones, pasarela, empresa_id=empresa_id, cliente_id=cliente_id, clave=clave)
    )
    await asyncio.wait_for(pasarela.llego.wait(), timeout=10)
    segundo = asyncio.create_task(
        _pedir(sesiones, pasarela, empresa_id=empresa_id, cliente_id=cliente_id, clave=clave)
    )
    await asyncio.sleep(0.3)  # deja que el segundo llegue al bloqueo
    pasarela.soltar.set()
    resultados = await asyncio.gather(primero, segundo, return_exceptions=True)

    assert not any(isinstance(uno, BaseException) for uno in resultados), resultados
    cobros = [uno for uno in resultados if isinstance(uno, Cobro)]
    assert cobros[0].id == cobros[1].id
    assert pasarela.creados == 1
    async with engine_dueno.connect() as conexion:
        total = (await conexion.execute(CONTAR, {"empresa_id": empresa_id})).scalar_one()
    assert total == 1


async def test_la_misma_clave_en_dos_empresas_son_dos_cobros_y_una_no_ve_la_de_la_otra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Caso 13. El índice y el bloqueo incluyen `empresa_id`; RLS acota la lectura."""
    empresa_a, cliente_a = await _empresa_con_cliente(engine_dueno)
    empresa_b, cliente_b = await _empresa_con_cliente(engine_dueno)
    clave = uuid.uuid4()

    de_a = await _pedir(
        sesiones, PasarelaFalsa(), empresa_id=empresa_a, cliente_id=cliente_a, clave=clave
    )
    de_b = await _pedir(
        sesiones, PasarelaFalsa(), empresa_id=empresa_b, cliente_id=cliente_b, clave=clave
    )

    assert de_a.id != de_b.id
    async with sesion_de_empresa(sesiones, empresa_b) as sesion:
        vista = await RepositorioCobroPostgres(sesion).buscar_por_clave_bloqueada(clave)
    assert vista is not None
    assert vista.id == de_b.id
    async with sesion_de_empresa(sesiones, empresa_a) as sesion:
        assert await RepositorioCobroPostgres(sesion).buscar_por_id(de_b.id) is None


async def test_una_clave_desconocida_no_encuentra_nada_ni_de_otra_empresa(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Una empresa no puede recuperar el cobro de otra adivinando su clave (RLS)."""
    empresa_a, cliente_a = await _empresa_con_cliente(engine_dueno)
    empresa_b, _ = await _empresa_con_cliente(engine_dueno)
    clave = uuid.uuid4()
    await _pedir(sesiones, PasarelaFalsa(), empresa_id=empresa_a, cliente_id=cliente_a, clave=clave)

    async with sesion_de_empresa(sesiones, empresa_b) as sesion:
        assert await RepositorioCobroPostgres(sesion).buscar_por_clave_bloqueada(clave) is None


async def test_el_indice_rechaza_la_segunda_fila_y_el_repositorio_la_traduce_a_409(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Caso 14. El respaldo del bloqueo: `PedidoEnCurso` (409), nunca un 500."""
    empresa_id, cliente_id = await _empresa_con_cliente(engine_dueno)
    clave = uuid.uuid4()
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioCobroPostgres(sesion).agregar(
            _cobro_con_clave(empresa_id, cliente_id, clave)
        )

    with pytest.raises(PedidoEnCurso):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await RepositorioCobroPostgres(sesion).agregar(
                _cobro_con_clave(empresa_id, cliente_id, clave)
            )


async def test_los_cobros_sin_clave_no_chocan_entre_si(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """El índice es parcial: `NULL` no cuenta, y los cobros anteriores a 0034 siguen siendo válidos."""
    empresa_id, cliente_id = await _empresa_con_cliente(engine_dueno)
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repo = RepositorioCobroPostgres(sesion)
        for _ in range(2):
            cobro = _cobro_con_clave(empresa_id, cliente_id, uuid.uuid4())
            cobro.clave_idempotencia = None
            await repo.agregar(cobro)
