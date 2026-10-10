"""`EnvioPorWhatsApp` dice si el fallo vale otro intento (U7, tramo ii, D-U7-3).

La clasificación la hace la raíz (`FallaDelCanal.transitoria`); el adaptador la copia al
`ResultadoDeEnvio`. Todo lo que el adaptador no entiende es permanente: reintentar a ciegas un
error propio repetiría el mismo fallo cada hora.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.payments.application.ports_envio import ContactoDeCobro, FallaDelCanal
from cheatsheet.contexts.payments.domain.cobro import Cobro
from cheatsheet.contexts.payments.infrastructure.envio import EnvioPorWhatsApp
from cheatsheet.shared.empresa import EmpresaId

from tests.contexts.payments.application.test_cobros_y_recordatorios import enviar_de_punta_a_punta

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())


class _Contactos:
    async def contacto_de(self, cliente_id: UUID) -> ContactoDeCobro:
        del cliente_id
        return ContactoDeCobro(nombre="Rosa Diaz", telefono="5491155550000")


class _SinPlantillas:
    async def para(self, codigo: str, variables: object) -> None:
        del codigo, variables


class _Canal:
    def __init__(self, falla: Exception | None) -> None:
        self._falla = falla

    async def enviar(self, *, telefono: str, texto: str) -> str:
        del telefono, texto
        if self._falla is not None:
            raise self._falla
        return "wamid.OK"

    async def enviar_plantilla(
        self, *, telefono: str, nombre: str, idioma: str, parametros: Mapping[str, str]
    ) -> str:
        del telefono, nombre, idioma, parametros
        return "wamid.OK"


async def _enviar(falla: Exception | None) -> tuple[bool, str | None]:
    cobro = Cobro(
        id=uuid4(),
        empresa_id=EMPRESA,
        cliente_id=uuid4(),
        monto=Decimal("10.00"),
        descripcion="Consulta",
        vence_el=AHORA,
        created_at=AHORA,
    )
    envio = EnvioPorWhatsApp(_Canal(falla), _Contactos(), _SinPlantillas())
    resultado = await enviar_de_punta_a_punta(
        envio, empresa_id=EMPRESA, cobro=cobro, canal="WHATSAPP", paso=1
    )
    return resultado.transitoria, resultado.codigo


async def test_una_falla_transitoria_del_canal_llega_marcada() -> None:
    assert await _enviar(FallaDelCanal("SATURADA", transitoria=True)) == (True, "SATURADA")


async def test_una_falla_permanente_del_canal_no_es_transitoria() -> None:
    assert await _enviar(FallaDelCanal("131026")) == (False, "131026")


async def test_un_error_que_el_adaptador_no_entiende_no_es_transitorio() -> None:
    assert await _enviar(RuntimeError("otra cosa")) == (False, "ERROR")


async def test_lo_que_sale_bien_no_es_transitorio() -> None:
    assert await _enviar(None) == (False, None)
