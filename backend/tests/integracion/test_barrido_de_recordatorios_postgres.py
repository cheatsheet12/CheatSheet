"""El barrido de recordatorios contra el motor: un fallo no deshace lo que ya salió (U5, H1 y H1b).

Desde U7 (tramo ii) cada recordatorio confirma su fila antes de hablar con Meta y su resultado
después (`ConfirmacionDeLaUnidad`): lo que ya salió queda confirmado aunque lo que sigue falle.

Dos defectos que sólo existen con una transacción real:

- **H1.** El barrido despacha todos los cobros de una empresa en **una sola transacción**. Si el
  cobro K levantaba, la unidad de trabajo descartaba también las filas de los cobros 1..K-1 —cuyos
  mensajes ya habían salido— y el barrido de la hora siguiente los mandaba de nuevo.
- **H1b.** En PostgreSQL un `IntegrityError` aborta la transacción. El «ya salió, seguí» del
  barrido atrapaba el duplicado del índice `(cobro_id, paso)` **sin savepoint**, así que la
  sesión quedaba inservible y el cobro siguiente reventaba.

Sin PostgreSQL se saltean; los confirma la CI del PR.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from cheatsheet.contexts.payments.application.errors import DespachoNoPersistido
from cheatsheet.contexts.payments.application.ports_de_recordatorios import (
    PortEnvioDeRecordatorio,
)
from cheatsheet.contexts.payments.application.recordatorios import DespacharRecordatorios
from cheatsheet.contexts.payments.domain.recordatorio import EstadoEntrega, Recordatorio
from cheatsheet.contexts.payments.infrastructure.aislamiento import AislamientoConSavepoint
from cheatsheet.contexts.payments.infrastructure.repositories import RepositorioCobroPostgres
from cheatsheet.contexts.payments.infrastructure.repositorio_recordatorio import (
    RepositorioRecordatoriosPostgres,
)
from cheatsheet.contexts.payments.infrastructure.transaccion import ConfirmacionDeLaUnidad
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.contexts.payments.application.test_cobros_y_recordatorios import (
    CadenaFalsa,
    EnvioFalso,
    EnvioQueFallaEn,
)
from tests.contexts.payments.application.test_confirmacion import PublicadorFalso
from tests.integracion.conftest import requiere_base
from tests.integracion.test_cobros_postgres import AHORA, _cliente, _cobro, _empresa, _guardar

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

DESPUES = AHORA + timedelta(days=4)


async def _tres_cobros(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> tuple[EmpresaId, list[uuid.UUID]]:
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    cobros = [
        _cobro(empresa_id, cliente_id, vence_en_dias=0, preferencia=f"pref-{n}") for n in range(3)
    ]
    await _guardar(sesiones, empresa_id, *cobros)
    return empresa_id, [uno.id for uno in cobros]


def _barrido(
    sesion: AsyncSession,
    empresa_id: EmpresaId,
    envio: PortEnvioDeRecordatorio,
    recordatorios: RepositorioRecordatoriosPostgres | None = None,
) -> DespacharRecordatorios:
    return DespacharRecordatorios(
        cobros=RepositorioCobroPostgres(sesion),
        recordatorios=recordatorios or RepositorioRecordatoriosPostgres(sesion),
        envio=envio,
        cadena=CadenaFalsa(),
        publicador=PublicadorFalso(),
        aislamiento=AislamientoConSavepoint(sesion),
        transaccion=ConfirmacionDeLaUnidad(sesion, empresa_id),
    )


async def _estados(
    sesiones: async_sessionmaker[AsyncSession], empresa_id: EmpresaId
) -> dict[uuid.UUID, list[str | None]]:
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        filas = await sesion.execute(
            text("SELECT cobro_id, estado_entrega FROM recordatorio ORDER BY paso")
        )
        agrupados: dict[uuid.UUID, list[str | None]] = {}
        for cobro_id, estado in filas:
            agrupados.setdefault(cobro_id, []).append(estado)
        return agrupados


async def test_dos_barridos_seguidos_mandan_un_solo_mensaje_por_cobro(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """**Caso 2 (H1).** El envío falla en el cobro 2 la primera vez. Antes, la primera
    transacción se deshacía entera y el cobro 1 recibía **dos** envíos."""
    empresa_id, (uno, dos, tres) = await _tres_cobros(sesiones, engine_dueno)
    envio = EnvioQueFallaEn(2)

    for _ in range(2):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await _barrido(sesion, empresa_id, envio).ejecutar(empresa_id=empresa_id, ahora=DESPUES)

    assert envio.llamadas == 3
    assert envio.enviados.count(uno) == 1
    assert envio.enviados.count(tres) == 1
    estados = await _estados(sesiones, empresa_id)
    assert estados[uno] == [EstadoEntrega.ENVIADO.value]
    assert estados[dos] == [EstadoEntrega.FALLIDO.value]
    assert estados[tres] == [EstadoEntrega.ENVIADO.value]


async def test_una_falla_de_base_en_el_savepoint_del_cobro_2_conserva_las_filas_de_1_y_3(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """**Caso 2 (H1), la parte de la base.** Una sentencia que la base rechaza adentro del
    savepoint del cobro 2 aborta esa porción y nada más."""
    empresa_id, (uno, dos, tres) = await _tres_cobros(sesiones, engine_dueno)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:

        class GuardaMal(RepositorioRecordatoriosPostgres):
            async def guardar(self, recordatorio: Recordatorio) -> None:
                if recordatorio.cobro_id == dos:
                    # Una sentencia que PostgreSQL rechaza: aborta la transacción salvo que
                    # corra dentro de un savepoint.
                    await sesion.execute(text("SELECT 1 / 0"))
                await super().guardar(recordatorio)

        resultado = await _barrido(sesion, empresa_id, EnvioFalso(), GuardaMal(sesion)).ejecutar(
            empresa_id=empresa_id, ahora=DESPUES
        )

    assert resultado.procesados == 2
    estados = await _estados(sesiones, empresa_id)
    assert estados[uno] == [EstadoEntrega.ENVIADO.value]
    assert estados[tres] == [EstadoEntrega.ENVIADO.value]
    # Su fila se reservó y confirmó **antes** del envío (U7, H1) y la base rechazó el resultado: queda
    # «en curso», sin estado de entrega. No se reenvía: vencida su ventana se resuelve `INCIERTO`.
    assert estados[dos] == [None]


async def test_un_duplicado_no_envenena_la_transaccion_del_barrido(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """**Caso 3 (H1b).** La fila del paso 1 del cobro A ya está; otro barrido la insertó entre
    que éste leyó y que intentó escribir. El barrido sigue, despacha el cobro B **en la misma
    transacción** y confirma."""
    empresa_id, (a, b, _tres) = await _tres_cobros(sesiones, engine_dueno)
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        previo = Recordatorio(id=uuid.uuid4(), cobro_id=a, paso=1, canal="WHATSAPP")
        previo.marcar_enviado(AHORA)
        await RepositorioRecordatoriosPostgres(sesion).agregar(previo)

    envio = EnvioFalso()
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:

        class NoVeLaFilaDeA(RepositorioRecordatoriosPostgres):
            async def de_cobros(
                self, cobro_ids: list[uuid.UUID]
            ) -> dict[uuid.UUID, list[Recordatorio]]:
                visibles = await super().de_cobros(cobro_ids)
                visibles.pop(a, None)  # la carrera: el barrido no la vio al leer
                return visibles

        resultado = await _barrido(sesion, empresa_id, envio, NoVeLaFilaDeA(sesion)).ejecutar(
            empresa_id=empresa_id, ahora=DESPUES
        )

    # A choca con el índice y no se manda; B y el tercero salen, con la sesión todavía usable.
    assert resultado.procesados == 2
    assert a not in {cobro for cobro, _, _ in envio.enviados}
    assert b in {cobro for cobro, _, _ in envio.enviados}
    estados = await _estados(sesiones, empresa_id)
    assert estados[b] == [EstadoEntrega.ENVIADO.value]


async def test_el_aislamiento_convierte_un_error_de_la_base_en_despacho_no_persistido(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        with pytest.raises(DespachoNoPersistido):
            async with AislamientoConSavepoint(sesion).aislar():
                await sesion.execute(text("SELECT 1 / 0"))
        # La transacción sigue viva después del error.
        assert (await sesion.execute(text("SELECT 1"))).scalar_one() == 1
