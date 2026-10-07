"""El reintento de recordatorios contra el motor (U7, tramo ii, casos 21 y H1).

Tres cosas que solo existen con transacciones reales:

- **H1.** Cuando el barrido llama a Meta, la fila del recordatorio **ya está confirmada**: otra
  transacción (la de un callback) la ve. Antes, todo se confirmaba al final de la empresa.
- **El reintento es un `UPDATE`** de la misma fila, y su espera sale del índice parcial.
- **Caso 21.** Dos barridos solapados con una fila pendiente mandan **un** solo mensaje: la fila se
  relee bloqueada (`FOR UPDATE`) y el que espera ve lo que el otro dejó confirmado.

Sin PostgreSQL se saltean; los confirma la CI del PR.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta

import pytest
from cheatsheet.contexts.payments.application.recordatorios import DespacharRecordatorios
from cheatsheet.contexts.payments.domain.recordatorio import VENTANA_DE_ENVIO
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

from tests.contexts.payments.application.dobles_de_reintento import (
    EnvioGuionado,
    enviado,
    transitoria,
)
from tests.contexts.payments.application.test_cobros_y_recordatorios import (
    CadenaFalsa,
    TransaccionFalsa,
)
from tests.contexts.payments.application.test_confirmacion import PublicadorFalso
from tests.integracion.conftest import requiere_base
from tests.integracion.test_cobros_postgres import AHORA, _cliente, _cobro, _empresa, _guardar

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

DESPUES = AHORA + timedelta(days=4)

FILAS = text(
    "SELECT id, intentos, enviado_en, estado_entrega, externo_id, ultimo_error, "
    "proximo_intento_en FROM recordatorio ORDER BY paso"
)


async def _un_cobro(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> EmpresaId:
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    await _guardar(sesiones, empresa_id, _cobro(empresa_id, cliente_id, vence_en_dias=0))
    return empresa_id


def _barrido(
    sesion: AsyncSession, empresa_id: EmpresaId, envio: EnvioGuionado
) -> DespacharRecordatorios:
    return DespacharRecordatorios(
        cobros=RepositorioCobroPostgres(sesion),
        recordatorios=RepositorioRecordatoriosPostgres(sesion),
        envio=envio,
        cadena=CadenaFalsa(),
        publicador=PublicadorFalso(),
        aislamiento=AislamientoConSavepoint(sesion),
        transaccion=ConfirmacionDeLaUnidad(sesion, empresa_id),
    )


async def _filas(
    sesiones: async_sessionmaker[AsyncSession], empresa_id: EmpresaId
) -> list[tuple[object, ...]]:
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        return [tuple(fila) for fila in await sesion.execute(FILAS)]


async def _barrer(
    sesiones: async_sessionmaker[AsyncSession],
    empresa_id: EmpresaId,
    envio: EnvioGuionado,
    ahora: datetime,
) -> None:
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await _barrido(sesion, empresa_id, envio).ejecutar(empresa_id=empresa_id, ahora=ahora)


async def test_cuando_el_barrido_llama_a_meta_la_fila_ya_esta_confirmada_para_otra_transaccion(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """**H1.** Es lo que ve un callback `failed` o `delivered` que llegue durante el barrido."""
    empresa_id = await _un_cobro(sesiones, engine_dueno)
    vistas: list[list[tuple[object, ...]]] = []
    envio = EnvioGuionado(TransaccionFalsa(), enviado("wamid-h1"))

    original = envio.enviar

    async def enviar_mirando(**kwargs: object) -> object:
        # Otra transacción, otra conexión: solo ve lo que el barrido ya confirmó.
        vistas.append(await _filas(sesiones, empresa_id))
        return await original(**kwargs)  # type: ignore[arg-type]

    envio.enviar = enviar_mirando  # type: ignore[method-assign,assignment]

    await _barrer(sesiones, empresa_id, envio, DESPUES)

    (visto,) = vistas
    assert len(visto) == 1
    _, intentos, enviado_en, estado, externo_id, _, proximo = visto[0]
    assert (intentos, enviado_en, estado, externo_id) == (1, None, None, None)
    assert proximo == DESPUES + VENTANA_DE_ENVIO
    (final,) = await _filas(sesiones, empresa_id)
    assert (final[3], final[4]) == ("ENVIADO", "wamid-h1")


async def test_el_reintento_actualiza_la_misma_fila_y_sale_con_su_wamid(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _un_cobro(sesiones, engine_dueno)
    envio = EnvioGuionado(TransaccionFalsa(), transitoria(), enviado("wamid-2"))

    await _barrer(sesiones, empresa_id, envio, DESPUES)
    (espera,) = await _filas(sesiones, empresa_id)
    assert (espera[1], espera[2], espera[5]) == (1, None, "SATURADA")
    assert espera[6] == DESPUES + timedelta(hours=1)

    await _barrer(sesiones, empresa_id, envio, DESPUES + timedelta(hours=1))

    (final,) = await _filas(sesiones, empresa_id)
    assert final[0] == espera[0]  # la misma fila: ningún `INSERT` nuevo
    assert (final[1], final[3], final[4], final[5], final[6]) == (
        2,
        "ENVIADO",
        "wamid-2",
        None,
        None,
    )
    assert envio.llamadas == 2


async def test_dos_barridos_solapados_con_una_fila_pendiente_mandan_una_sola_vez(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """**Caso 21.** La fila espera su reintento; dos workers la encuentran a la vez."""
    empresa_id = await _un_cobro(sesiones, engine_dueno)
    await _barrer(sesiones, empresa_id, EnvioGuionado(TransaccionFalsa(), transitoria()), DESPUES)
    envio = EnvioGuionado(TransaccionFalsa(), enviado("wamid-21"), enviado("wamid-21-bis"))
    cuando = DESPUES + timedelta(hours=1)

    await asyncio.gather(
        _barrer(sesiones, empresa_id, envio, cuando),
        _barrer(sesiones, empresa_id, envio, cuando),
    )

    assert envio.llamadas == 1
    (final,) = await _filas(sesiones, empresa_id)
    assert final[1] == 2
    assert final[3] == "ENVIADO"


async def test_un_envio_perdido_se_resuelve_incierto_y_no_se_reenvia(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """El proceso murió después de reservar: la fila quedó «en curso» y su ventana venció."""
    empresa_id = await _un_cobro(sesiones, engine_dueno)
    morir = EnvioGuionado(TransaccionFalsa(), asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await _barrer(sesiones, empresa_id, morir, DESPUES)
    (en_curso,) = await _filas(sesiones, empresa_id)
    assert (en_curso[1], en_curso[2]) == (1, None)  # la reserva quedó confirmada

    envio = EnvioGuionado(TransaccionFalsa(), enviado())
    await _barrer(sesiones, empresa_id, envio, DESPUES + VENTANA_DE_ENVIO + timedelta(minutes=1))

    (final,) = await _filas(sesiones, empresa_id)
    assert envio.llamadas == 0
    assert (final[3], final[5]) == ("FALLIDO", "INCIERTO")
    assert final[2] is not None
    assert uuid.UUID(str(final[0])) == uuid.UUID(str(en_curso[0]))
