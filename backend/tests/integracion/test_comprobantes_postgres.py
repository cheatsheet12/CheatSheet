"""El comprobante contra el motor: aislamiento, correlatividad y las garantías del esquema.

Cuatro cosas se prueban acá porque **ninguna de las cuatro existe fuera de PostgreSQL**:

1. El aislamiento por empresa. Un comprobante lleva CUIT, razón social y montos de un
   cliente: que una empresa vea los de otra no es un bug de listado, es una filtración de
   datos fiscales de terceros.
2. El índice único `(punto, tipo, numero)`, que es la última línea de defensa de D14.
3. Los `CHECK` que el agregado ya impone, escritos también en el esquema porque son los
   hechos que un bug futuro podría romper sin que nadie se entere hasta una inspección.
4. La función `SECURITY DEFINER` del barrido de D17, que por definición se ejecuta **sin**
   empresa declarada y tiene que seguir sin filtrar nada más que ids.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from cheatsheet.contexts.billing.application.ports import FiltrosDeComprobante
from cheatsheet.contexts.billing.domain.comprobante import (
    CAE,
    AlicuotaIVA,
    Comprobante,
    EstadoComprobante,
    ItemDeComprobante,
    Receptor,
)
from cheatsheet.contexts.billing.domain.punto_de_venta import PuntoDeVenta, TipoComprobante
from cheatsheet.contexts.billing.infrastructure.repositories import (
    RepositorioPuntoDeVentaPostgres,
)
from cheatsheet.contexts.billing.infrastructure.repositorio_comprobante import (
    RepositorioComprobantePostgres,
    empresas_con_comprobantes_en_vuelo,
)
from cheatsheet.platform.database import sesion_de_empresa, sesion_sin_empresa
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.fiscal import CondicionIVA
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError
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


async def _punto(
    sesiones: async_sessionmaker[AsyncSession], empresa_id: EmpresaId, numero: int = 1
) -> PuntoDeVenta:
    punto = PuntoDeVenta(id=uuid.uuid4(), empresa_id=empresa_id, numero=numero, created_at=AHORA)
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioPuntoDeVentaPostgres(sesion).agregar(punto)
    return punto


def _comprobante(
    empresa_id: EmpresaId,
    cliente_id: uuid.UUID,
    punto: PuntoDeVenta,
    *,
    numero: int | None = None,
    estado: EstadoComprobante = EstadoComprobante.BORRADOR,
    tipo: TipoComprobante = TipoComprobante.FACTURA_A,
) -> Comprobante:
    comprobante = Comprobante(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        cliente_id=cliente_id,
        punto_de_venta_id=punto.id,
        tipo=tipo,
        # La condición del receptor sale de la **letra** del comprobante, no al revés: un
        # Responsable Inscripto recibe A y un Consumidor Final recibe B, y armar el par al
        # azar produciría un agregado que `validar()` rechaza con razón (RN-01).
        receptor=Receptor(
            nombre="Acme SA",
            cuit="30712345671",
            condicion_iva=RI if tipo.letra == "A" else CondicionIVA.CONSUMIDOR_FINAL,
        ),
        emisor_condicion_iva=RI,
        created_at=AHORA,
    )
    comprobante.agregar_item(
        ItemDeComprobante(
            id=uuid.uuid4(),
            descripcion="Corte de pelo",
            cantidad=Decimal("2"),
            precio_unitario=Decimal("1000.00"),
            alicuota_iva=AlicuotaIVA.GENERAL,
        )
    )
    if estado is not EstadoComprobante.BORRADOR:
        comprobante.validar()
        if numero is not None:
            comprobante.enviar_a_arca(numero, AHORA)
        if estado is EstadoComprobante.AUTORIZADO:
            comprobante.autorizar(UN_CAE)
    return comprobante


async def _guardar(
    sesiones: async_sessionmaker[AsyncSession], empresa_id: EmpresaId, comprobante: Comprobante
) -> None:
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioComprobantePostgres(sesion).agregar(comprobante)


# ------------------------------------------------------------------ ida y vuelta


async def test_un_comprobante_sobrevive_entero_a_la_ida_y_vuelta(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Los montos vuelven como `Decimal` con dos decimales, no como `float`.

    Es el test que ata `CLAUDE.md` §3.5 al esquema: si alguien cambiara la columna a
    `FLOAT`, esto se caería con un total que difiere en el cuarto decimal.
    """
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    punto = await _punto(sesiones, empresa_id)
    comprobante = _comprobante(
        empresa_id, cliente_id, punto, numero=1, estado=EstadoComprobante.AUTORIZADO
    )
    await _guardar(sesiones, empresa_id, comprobante)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        leido = await RepositorioComprobantePostgres(sesion).buscar_por_id(comprobante.id)

    assert leido is not None
    assert leido.total == Decimal("2420.00")
    assert isinstance(leido.total, Decimal)
    assert leido.subtotal + leido.total_iva == leido.total
    assert leido.cae == UN_CAE
    assert leido.receptor.condicion_iva is RI
    assert [item.descripcion for item in leido.items] == ["Corte de pelo"]
    assert leido.items[0].alicuota_iva is AlicuotaIVA.GENERAL


async def test_editar_un_borrador_reescribe_sus_items_sin_dejar_huerfanos(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """El repositorio reescribe las líneas en vez de diferenciarlas.

    Es más seguro que un diff —que es la forma que pierde una línea sin avisar— y sólo es
    correcto porque el agregado se niega a tocar los ítems de algo pasado `VALIDADO`.
    """
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    punto = await _punto(sesiones, empresa_id)
    comprobante = _comprobante(empresa_id, cliente_id, punto)
    await _guardar(sesiones, empresa_id, comprobante)

    comprobante.agregar_item(
        ItemDeComprobante(
            id=uuid.uuid4(),
            descripcion="Barba",
            cantidad=Decimal("1"),
            precio_unitario=Decimal("500.00"),
            alicuota_iva=AlicuotaIVA.GENERAL,
        )
    )
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioComprobantePostgres(sesion).guardar(comprobante)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        leido = await RepositorioComprobantePostgres(sesion).buscar_por_id(comprobante.id)
        huerfanos = await sesion.execute(
            text("SELECT count(*) FROM item_de_comprobante WHERE comprobante_id = :id"),
            {"id": comprobante.id},
        )

    assert leido is not None
    assert len(leido.items) == 2
    assert huerfanos.scalar_one() == 2


# ------------------------------------------------------------------ la correlatividad


async def test_dos_comprobantes_con_el_mismo_numero_y_tipo_se_rechazan(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """La última línea de defensa de D14, en el esquema.

    El candado de `tomar_para_emitir` hace la carrera imposible; esto hace imposible
    equivocarse en eso sin que la base lo note.
    """
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    punto = await _punto(sesiones, empresa_id)
    await _guardar(
        sesiones,
        empresa_id,
        _comprobante(empresa_id, cliente_id, punto, numero=7, estado=EstadoComprobante.AUTORIZADO),
    )

    with pytest.raises(IntegrityError):
        await _guardar(
            sesiones,
            empresa_id,
            _comprobante(
                empresa_id, cliente_id, punto, numero=7, estado=EstadoComprobante.AUTORIZADO
            ),
        )


async def test_el_numero_de_un_rechazado_se_puede_volver_a_emitir(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Un rechazo devuelve el número (ARCA no lo consumió): el siguiente lo toma sin choque."""
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    punto = await _punto(sesiones, empresa_id)
    rechazado = _comprobante(
        empresa_id, cliente_id, punto, numero=2, estado=EstadoComprobante.ENVIADO_A_ARCA
    )
    rechazado.rechazar("Error 10246: algo")
    await _guardar(sesiones, empresa_id, rechazado)

    await _guardar(
        sesiones,
        empresa_id,
        _comprobante(
            empresa_id, cliente_id, punto, numero=2, estado=EstadoComprobante.ENVIADO_A_ARCA
        ),
    )


async def test_el_mismo_numero_en_dos_tipos_distintos_convive(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """HU-E5-05 RN-02: la numeración es por punto **y por tipo**.

    La factura A número 5 y la factura B número 5 son dos comprobantes legítimos. Un índice
    sobre `(empresa, numero)` los habría rechazado, que es el error que este test impide.
    """
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    punto = await _punto(sesiones, empresa_id)

    for tipo in (TipoComprobante.FACTURA_A, TipoComprobante.FACTURA_B):
        await _guardar(
            sesiones,
            empresa_id,
            _comprobante(
                empresa_id,
                cliente_id,
                punto,
                numero=5,
                tipo=tipo,
                estado=EstadoComprobante.AUTORIZADO,
            ),
        )

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        todos = await RepositorioComprobantePostgres(sesion).listar(FiltrosDeComprobante())
    assert len(todos) == 2


async def test_dos_borradores_sin_numero_no_son_un_duplicado(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """El índice es parcial: `WHERE numero IS NOT NULL`.

    Sin eso, el segundo borrador chocaría contra el primero por tener los dos `numero` en
    `NULL` — y una pantalla que no deja empezar un segundo comprobante es difícil de
    diagnosticar como «índice mal declarado».
    """
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    punto = await _punto(sesiones, empresa_id)

    await _guardar(sesiones, empresa_id, _comprobante(empresa_id, cliente_id, punto))
    await _guardar(sesiones, empresa_id, _comprobante(empresa_id, cliente_id, punto))

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        todos = await RepositorioComprobantePostgres(sesion).listar(FiltrosDeComprobante())
    assert len(todos) == 2


# ------------------------------------------------------------------ el aislamiento


async def test_una_empresa_no_ve_los_comprobantes_de_otra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """HU-E5-01 RN-01. Un comprobante lleva CUIT, razón social y montos de un tercero."""
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)
    cliente_a = await _cliente(engine_dueno, empresa_a)
    punto_a = await _punto(sesiones, empresa_a)
    comprobante = _comprobante(
        empresa_a, cliente_a, punto_a, numero=1, estado=EstadoComprobante.AUTORIZADO
    )
    await _guardar(sesiones, empresa_a, comprobante)

    async with sesion_de_empresa(sesiones, empresa_b) as sesion:
        repo = RepositorioComprobantePostgres(sesion)
        assert await repo.buscar_por_id(comprobante.id) is None
        assert await repo.listar(FiltrosDeComprobante()) == []


async def test_los_items_tampoco_cruzan_la_frontera(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """`item_de_comprobante` no tiene `empresa_id` propio: su política pasa por el padre.

    Es la parte de la migración que más fácil sería equivocar, porque una tabla sin
    `empresa_id` *parece* global — y esta lleva la descripción y el precio de cada línea.
    """
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)
    cliente_a = await _cliente(engine_dueno, empresa_a)
    punto_a = await _punto(sesiones, empresa_a)
    comprobante = _comprobante(empresa_a, cliente_a, punto_a)
    await _guardar(sesiones, empresa_a, comprobante)

    async with sesion_de_empresa(sesiones, empresa_b) as sesion:
        filas = await sesion.execute(text("SELECT count(*) FROM item_de_comprobante"))
    assert filas.scalar_one() == 0


async def test_no_se_puede_borrar_un_comprobante(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Un comprobante autorizado es un registro legal: se anula, no se borra."""
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    punto = await _punto(sesiones, empresa_id)
    comprobante = _comprobante(empresa_id, cliente_id, punto)
    await _guardar(sesiones, empresa_id, comprobante)

    with pytest.raises(ProgrammingError):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await sesion.execute(
                text("DELETE FROM comprobante WHERE id = :id"), {"id": comprobante.id}
            )


# ------------------------------------------------------------------ los CHECK


async def test_un_cae_sin_estado_autorizado_es_rechazado_por_el_esquema(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """El agregado ya lo impide; el `CHECK` está por si un bug futuro no.

    Es el hecho que nadie notaría hasta una inspección: un comprobante en `BORRADOR` con un
    CAE encima no falla nada, no rompe ninguna pantalla, y es una inconsistencia fiscal.
    """
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    punto = await _punto(sesiones, empresa_id)
    comprobante = _comprobante(empresa_id, cliente_id, punto)
    await _guardar(sesiones, empresa_id, comprobante)

    with pytest.raises(IntegrityError):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await sesion.execute(
                text(
                    "UPDATE comprobante SET cae_codigo = '7512', "
                    "cae_fecha_vencimiento = :vence WHERE id = :id"
                ),
                {"id": comprobante.id, "vence": UN_CAE.vence_el},
            )


async def test_una_factura_no_puede_tener_comprobante_de_origen(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """HU-E5-04 RN-01, escrita en el esquema: sólo una nota de crédito anula algo.

    Es el `CHECK` condicional que ADR-010 pone en lugar de una segunda tabla.
    """
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    punto = await _punto(sesiones, empresa_id)
    original = _comprobante(
        empresa_id, cliente_id, punto, numero=1, estado=EstadoComprobante.AUTORIZADO
    )
    otra = _comprobante(empresa_id, cliente_id, punto)
    await _guardar(sesiones, empresa_id, original)
    await _guardar(sesiones, empresa_id, otra)

    with pytest.raises(IntegrityError):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await sesion.execute(
                text("UPDATE comprobante SET comprobante_origen_id = :origen WHERE id = :id"),
                {"id": otra.id, "origen": original.id},
            )


# ------------------------------------------------------------------ el barrido de D17


async def test_el_barrido_ve_las_empresas_con_algo_en_vuelo_y_nada_mas(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """La sexta función `SECURITY DEFINER` del sistema.

    Corre **sin empresa declarada** —tiene que, o vería una sola— y por eso lo que devuelve
    importa tanto: ids de empresa y nada más. Un comprobante autorizado no la hace aparecer;
    uno en vuelo sí.
    """
    con_vuelo = await _empresa(engine_dueno)
    sin_vuelo = await _empresa(engine_dueno)
    cliente_uno = await _cliente(engine_dueno, con_vuelo)
    cliente_dos = await _cliente(engine_dueno, sin_vuelo)
    punto_uno = await _punto(sesiones, con_vuelo)
    punto_dos = await _punto(sesiones, sin_vuelo)

    await _guardar(
        sesiones,
        con_vuelo,
        _comprobante(
            con_vuelo, cliente_uno, punto_uno, numero=1, estado=EstadoComprobante.ENVIADO_A_ARCA
        ),
    )
    await _guardar(
        sesiones,
        sin_vuelo,
        _comprobante(
            sin_vuelo, cliente_dos, punto_dos, numero=1, estado=EstadoComprobante.AUTORIZADO
        ),
    )

    async with sesion_sin_empresa(sesiones) as sesion:
        empresas = await empresas_con_comprobantes_en_vuelo(sesion)

    assert con_vuelo in empresas
    assert sin_vuelo not in empresas


async def test_en_vuelo_respeta_la_ventana_y_el_aislamiento(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """La ventana existe para no arrebatarle el comprobante a la tarea que lo espera."""
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    punto = await _punto(sesiones, empresa_id)
    comprobante = _comprobante(
        empresa_id, cliente_id, punto, numero=1, estado=EstadoComprobante.ENVIADO_A_ARCA
    )
    await _guardar(sesiones, empresa_id, comprobante)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repo = RepositorioComprobantePostgres(sesion)
        recien = await repo.en_vuelo(anteriores_a=AHORA)
        viejos = await repo.en_vuelo(anteriores_a=datetime(2026, 9, 8, tzinfo=UTC))

    assert recien == []
    assert [c.id for c in viejos] == [comprobante.id]


# ------------------------------------------------------------------ el listado


async def test_el_listado_ordena_por_fecha_descendente_con_los_borradores_al_final(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """RN-03, y el `nulls_last` que no es cosmético.

    PostgreSQL pone los `NULL` **primero** en un orden descendente, así que sin
    `nulls_last` cada borrador sin terminar flotaría por encima de los comprobantes que
    alguien vino a ver.
    """
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    punto = await _punto(sesiones, empresa_id)

    borrador = _comprobante(empresa_id, cliente_id, punto)
    viejo = _comprobante(
        empresa_id, cliente_id, punto, numero=1, estado=EstadoComprobante.AUTORIZADO
    )
    nuevo = _comprobante(
        empresa_id, cliente_id, punto, numero=2, estado=EstadoComprobante.AUTORIZADO
    )
    nuevo.fecha_emision = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)

    for uno in (borrador, viejo, nuevo):
        await _guardar(sesiones, empresa_id, uno)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        listado = await RepositorioComprobantePostgres(sesion).listar(FiltrosDeComprobante())

    assert [c.id for c in listado] == [nuevo.id, viejo.id, borrador.id]


async def test_los_filtros_de_la_historia_funcionan_juntos(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """HU-E5-01 RN-02: rango de fechas, tipo y estado."""
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    punto = await _punto(sesiones, empresa_id)

    autorizada = _comprobante(
        empresa_id, cliente_id, punto, numero=1, estado=EstadoComprobante.AUTORIZADO
    )
    rechazada = _comprobante(
        empresa_id,
        cliente_id,
        punto,
        numero=2,
        tipo=TipoComprobante.FACTURA_B,
        estado=EstadoComprobante.ENVIADO_A_ARCA,
    )
    rechazada.rechazar("Error 10016: algo")
    for uno in (autorizada, rechazada):
        await _guardar(sesiones, empresa_id, uno)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repo = RepositorioComprobantePostgres(sesion)
        por_estado = await repo.listar(FiltrosDeComprobante(estados=(EstadoComprobante.RECHAZADO,)))
        por_tipo = await repo.listar(FiltrosDeComprobante(tipos=(TipoComprobante.FACTURA_A,)))
        fuera_de_rango = await repo.listar(FiltrosDeComprobante(desde=date(2026, 10, 1)))

    assert [c.id for c in por_estado] == [rechazada.id]
    assert [c.id for c in por_tipo] == [autorizada.id]
    assert fuera_de_rango == []
