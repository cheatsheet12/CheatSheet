"""`HorarioViaConfiguracion`: el ACL del horario de atención (caso 36 del plan).

Traduce `ConsultarAtencion` de `business_config` al vocabulario de `conversational`, y **una
configuración ilegible no voltea el webhook** (T11): un 500 haría que Meta reintente y el cliente no
reciba nada, así que se trata como «sin horario» y se registra.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.business_config.application.atencion import ConsultarAtencion
from cheatsheet.contexts.business_config.domain.regla import ReglaDeNegocio, TipoRegla
from cheatsheet.contexts.conversational.domain.fuera_de_horario import PoliticaFueraDeHorario
from cheatsheet.contexts.conversational.infrastructure.horario import HorarioViaConfiguracion
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.zona_horaria import ZONA_ARGENTINA
from structlog.testing import capture_logs

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())
#: Lunes 05/10/2026 22:00 en Argentina.
AHORA = datetime(2026, 10, 5, 22, 0, tzinfo=ZONA_ARGENTINA)


class ReglasFalsas:
    def __init__(self, *reglas: ReglaDeNegocio) -> None:
        self.guardadas = {uno.id: uno for uno in reglas}

    async def agregar(self, regla: ReglaDeNegocio) -> None:
        self.guardadas[regla.id] = regla

    async def guardar(self, regla: ReglaDeNegocio) -> None:
        self.guardadas[regla.id] = regla

    async def buscar_por_id(self, regla_id: UUID) -> ReglaDeNegocio | None:
        return self.guardadas.get(regla_id)

    async def listar(self, tipo: TipoRegla | None = None) -> list[ReglaDeNegocio]:
        return [una for una in self.guardadas.values() if tipo is None or una.tipo is tipo]


def _regla(configuracion: dict[str, object]) -> ReglaDeNegocio:
    return ReglaDeNegocio(
        id=uuid4(),
        empresa_id=EMPRESA,
        tipo=TipoRegla.HORARIO_DE_ATENCION,
        configuracion=configuracion,
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
    )


def _acl(*reglas: ReglaDeNegocio) -> HorarioViaConfiguracion:
    return HorarioViaConfiguracion(ConsultarAtencion(ReglasFalsas(*reglas)), empresa_id=EMPRESA)


def _horario(politica: str, **cambios: object) -> dict[str, object]:
    base: dict[str, object] = {
        "version": 1,
        "politica": politica,
        "dias": [
            {"dia": dia, "franjas": [{"desde": "09:00", "hasta": "19:00"}]} for dia in range(5)
        ],
        "fechas_cerradas": [],
    }
    base.update(cambios)
    return base


async def test_sin_regla_el_negocio_esta_abierto() -> None:
    atencion = await _acl().consultar(AHORA)

    assert atencion.abierto is True
    assert atencion.politica is PoliticaFueraDeHorario.AGENTE_RESPONDE


async def test_la_politica_de_business_config_se_traduce_al_enum_propio() -> None:
    atencion = await _acl(_regla(_horario("MENSAJE_FIJO"))).consultar(AHORA)

    assert atencion.abierto is False
    assert atencion.politica is PoliticaFueraDeHorario.MENSAJE_FIJO
    assert type(atencion.politica) is PoliticaFueraDeHorario
    assert atencion.proxima_apertura == datetime(2026, 10, 6, 9, 0, tzinfo=ZONA_ARGENTINA)
    assert atencion.cerrado_desde == datetime(2026, 10, 5, 19, 0, tzinfo=ZONA_ARGENTINA)


async def test_la_politica_por_defecto_tambien_se_traduce() -> None:
    atencion = await _acl(_regla(_horario("AGENTE_RESPONDE"))).consultar(AHORA)

    assert atencion.politica is PoliticaFueraDeHorario.AGENTE_RESPONDE


async def test_sin_apertura_en_el_horizonte_pasa_como_none() -> None:
    sin_regreso = _horario(
        "MENSAJE_FIJO",
        dias=[{"dia": 0, "franjas": [{"desde": "09:00", "hasta": "19:00"}]}],
        fechas_cerradas=[(date(2026, 10, 12) + timedelta(weeks=n)).isoformat() for n in range(53)],
    )

    atencion = await _acl(_regla(sin_regreso)).consultar(AHORA)

    assert atencion.abierto is False
    assert atencion.proxima_apertura is None


async def test_una_configuracion_ilegible_se_trata_como_sin_horario_y_se_registra() -> None:
    ilegible = _regla({"version": 1, "politica": "SILENCIO", "dias": "lunes"})

    with capture_logs() as registros:
        atencion = await _acl(ilegible).consultar(AHORA)

    assert atencion.abierto is True
    assert atencion.politica is PoliticaFueraDeHorario.AGENTE_RESPONDE
    assert [uno["event"] for uno in registros] == ["horario_ilegible"]
