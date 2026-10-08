"""`AgendaViaConfiguracion` — el ACL de la agenda de recordatorios (U8, D-U8-5, D-U8-14)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.business_config.application.agenda import ConsultarAgendaDeNotificacion
from cheatsheet.contexts.business_config.domain.regla import ReglaDeNegocio, TipoRegla
from cheatsheet.contexts.scheduling.application.errors import AgendaDeNotificacionInvalida
from cheatsheet.contexts.scheduling.infrastructure.agenda_de_notificacion import (
    AgendaViaConfiguracion,
)
from cheatsheet.shared.empresa import EmpresaId

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())


class _Reglas:
    def __init__(self, *reglas: ReglaDeNegocio) -> None:
        self._reglas = list(reglas)

    async def listar(self, tipo: TipoRegla | None = None) -> list[ReglaDeNegocio]:
        return [una for una in self._reglas if tipo is None or una.tipo is tipo]

    async def buscar_por_id(self, regla_id: UUID) -> ReglaDeNegocio | None:
        return next((una for una in self._reglas if una.id == regla_id), None)


def _regla(configuracion: dict[str, object], *, activa: bool = True) -> ReglaDeNegocio:
    return ReglaDeNegocio(
        id=uuid4(),
        empresa_id=EMPRESA,
        tipo=TipoRegla.AGENDA_DE_NOTIFICACION,
        configuracion=configuracion,
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
        activa=activa,
    )


def _agenda(*reglas: ReglaDeNegocio) -> AgendaViaConfiguracion:
    consulta = ConsultarAgendaDeNotificacion(_Reglas(*reglas))  # type: ignore[arg-type]
    return AgendaViaConfiguracion(consulta, empresa_id=EMPRESA)


async def test_sin_regla_rige_el_default_de_24_horas() -> None:
    assert await _agenda().anticipaciones() == (24 * 60,)


async def test_con_la_regla_configurada_devuelve_sus_anticipaciones_en_minutos() -> None:
    regla = _regla({"recordatorios": [{"horas_antes": 2}, {"horas_antes": 48}]})

    assert await _agenda(regla).anticipaciones() == (48 * 60, 2 * 60)


async def test_con_la_regla_desactivada_los_recordatorios_estan_apagados() -> None:
    regla = _regla({"recordatorios": [{"horas_antes": 24}]}, activa=False)

    assert await _agenda(regla).anticipaciones() == ()


async def test_una_regla_malformada_se_traduce_con_su_id_y_sin_su_contenido() -> None:
    regla = _regla({"recordatorios": "SECRETO"})

    with pytest.raises(AgendaDeNotificacionInvalida) as exc:
        await _agenda(regla).anticipaciones()

    assert exc.value.regla_id == regla.id
    assert "SECRETO" not in str(exc.value)
