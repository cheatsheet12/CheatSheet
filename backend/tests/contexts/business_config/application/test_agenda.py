"""HU-E11-01 — configurar y consultar la agenda de notificación (casos 5 a 7)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.business_config.application.agenda import (
    AgendaVigente,
    ConfigurarAgendaDeNotificacion,
    ConsultarAgendaDeNotificacion,
    configuracion_de_agenda_desde,
)
from cheatsheet.contexts.business_config.application.errors import AgendaMalFormada
from cheatsheet.contexts.business_config.application.reglas import MOTIVO_SOLO_ADMIN
from cheatsheet.contexts.business_config.domain.agenda_de_notificacion import (
    AnticipacionDeRecordatorio,
    ConfiguracionDeAgenda,
)
from cheatsheet.contexts.business_config.domain.regla import ReglaDeNegocio, TipoRegla
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, OperacionNoPermitida
from cheatsheet.shared.events import EventoDeDominio
from cheatsheet.shared.roles import RolUsuario

EMPRESA = EmpresaId(uuid4())
USUARIO = UsuarioId(uuid4())
AHORA = datetime(2026, 10, 5, 22, 0, tzinfo=UTC)


class ReglasFalsas:
    def __init__(self) -> None:
        self.guardadas: dict[UUID, ReglaDeNegocio] = {}

    async def agregar(self, regla: ReglaDeNegocio) -> None:
        self.guardadas[regla.id] = regla

    async def guardar(self, regla: ReglaDeNegocio) -> None:
        self.guardadas[regla.id] = regla

    async def buscar_por_id(self, regla_id: UUID) -> ReglaDeNegocio | None:
        return self.guardadas.get(regla_id)

    async def listar(self, tipo: TipoRegla | None = None) -> list[ReglaDeNegocio]:
        return [una for una in self.guardadas.values() if tipo is None or una.tipo is tipo]


class PublicadorFalso:
    def __init__(self) -> None:
        self.eventos: list[EventoDeDominio] = []

    async def publicar(self, evento: EventoDeDominio) -> None:
        self.eventos.append(evento)


def _config(*horas: int) -> ConfiguracionDeAgenda:
    return ConfiguracionDeAgenda(tuple(AnticipacionDeRecordatorio(h) for h in horas))


def _guardar(
    reglas: ReglasFalsas,
    publicador: PublicadorFalso,
    configuracion: ConfiguracionDeAgenda,
    *,
    rol: RolUsuario = RolUsuario.ADMINISTRADOR,
    prioridad: int = 0,
) -> Any:
    return ConfigurarAgendaDeNotificacion(reglas=reglas, publicador=publicador).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=rol,
        configuracion=configuracion,
        ahora=AHORA,
        prioridad=prioridad,
    )


def _regla(
    configuracion: ConfiguracionDeAgenda,
    *,
    prioridad: int = 0,
    activa: bool = True,
    creada: datetime = datetime(2026, 10, 1, tzinfo=UTC),
) -> ReglaDeNegocio:
    return ReglaDeNegocio(
        id=uuid4(),
        empresa_id=EMPRESA,
        tipo=TipoRegla.AGENDA_DE_NOTIFICACION,
        configuracion=configuracion.como_json(),
        created_at=creada,
        prioridad=prioridad,
        activa=activa,
    )


# --------------------------------------------------------------------- caso 5


@pytest.mark.asyncio
async def test_crea_la_regla_y_un_segundo_guardado_la_reemplaza() -> None:
    reglas, publicador = ReglasFalsas(), PublicadorFalso()

    primera = await _guardar(reglas, publicador, _config(24))
    segunda = await _guardar(reglas, publicador, _config(48, 2), prioridad=2)

    assert primera.id == segunda.id
    assert len(reglas.guardadas) == 1
    assert segunda.tipo is TipoRegla.AGENDA_DE_NOTIFICACION
    assert segunda.configuracion == {"recordatorios": [{"horas_antes": 48}, {"horas_antes": 2}]}
    assert segunda.prioridad == 2
    assert [evento.accion for evento in publicador.eventos] == [  # type: ignore[attr-defined]
        "alta_regla_de_agenda",
        "editar_regla_de_agenda",
    ]


@pytest.mark.asyncio
async def test_guardar_una_regla_desactivada_la_reactiva() -> None:
    reglas, publicador = ReglasFalsas(), PublicadorFalso()
    regla = _regla(_config(24), activa=False)
    await reglas.agregar(regla)

    guardada = await _guardar(reglas, publicador, _config(12))

    assert guardada.id == regla.id
    assert guardada.activa is True


@pytest.mark.asyncio
async def test_actualizar_con_prioridad_negativa_se_rechaza_y_no_toca_la_regla() -> None:
    reglas, publicador = ReglasFalsas(), PublicadorFalso()
    existente = await _guardar(reglas, publicador, _config(24), prioridad=3)

    with pytest.raises(EntradaInvalida) as exc:
        await _guardar(reglas, publicador, _config(12), prioridad=-1)

    assert str(exc.value) == "La prioridad de una regla no puede ser negativa"
    assert reglas.guardadas[existente.id].prioridad == 3
    assert reglas.guardadas[existente.id].configuracion == _config(24).como_json()
    assert len(publicador.eventos) == 1


@pytest.mark.asyncio
async def test_un_operador_no_puede_configurar_la_agenda() -> None:
    reglas, publicador = ReglasFalsas(), PublicadorFalso()

    with pytest.raises(OperacionNoPermitida) as exc:
        await _guardar(reglas, publicador, _config(24), rol=RolUsuario.OPERADOR)

    assert str(exc.value) == MOTIVO_SOLO_ADMIN
    assert reglas.guardadas == {}
    assert publicador.eventos == []


# --------------------------------------------------------------------- caso 6


@pytest.mark.asyncio
async def test_sin_regla_rige_el_default_de_24_horas_y_no_esta_configurada() -> None:
    agenda = await ConsultarAgendaDeNotificacion(ReglasFalsas()).ejecutar(empresa_id=EMPRESA)

    assert agenda == AgendaVigente(anticipaciones_min=(24 * 60,), configurada=False)


@pytest.mark.asyncio
async def test_con_regla_devuelve_sus_anticipaciones_en_minutos() -> None:
    reglas = ReglasFalsas()
    await reglas.agregar(_regla(_config(2, 48)))

    agenda = await ConsultarAgendaDeNotificacion(reglas).ejecutar(empresa_id=EMPRESA)

    assert agenda == AgendaVigente(anticipaciones_min=(48 * 60, 2 * 60), configurada=True)


@pytest.mark.asyncio
async def test_la_regla_desactivada_apaga_los_recordatorios_sin_volver_al_default() -> None:
    reglas = ReglasFalsas()
    await reglas.agregar(_regla(_config(24), activa=False))

    agenda = await ConsultarAgendaDeNotificacion(reglas).ejecutar(empresa_id=EMPRESA)

    assert agenda == AgendaVigente(anticipaciones_min=(), configurada=True)


@pytest.mark.asyncio
async def test_una_desactivada_no_tapa_a_otra_activa() -> None:
    reglas = ReglasFalsas()
    await reglas.agregar(_regla(_config(24), activa=False, prioridad=9))
    await reglas.agregar(_regla(_config(6), prioridad=1))

    agenda = await ConsultarAgendaDeNotificacion(reglas).ejecutar(empresa_id=EMPRESA)

    assert agenda == AgendaVigente(anticipaciones_min=(6 * 60,), configurada=True)


# --------------------------------------------------------------------- caso 7


@pytest.mark.asyncio
async def test_con_dos_reglas_rige_la_de_mayor_prioridad_y_a_igualdad_la_mas_reciente() -> None:
    reglas = ReglasFalsas()
    await reglas.agregar(_regla(_config(24), prioridad=1))
    await reglas.agregar(_regla(_config(3), prioridad=5))
    agenda = await ConsultarAgendaDeNotificacion(reglas).ejecutar(empresa_id=EMPRESA)
    assert agenda.anticipaciones_min == (3 * 60,)

    reglas = ReglasFalsas()
    await reglas.agregar(_regla(_config(24), creada=datetime(2026, 10, 1, tzinfo=UTC)))
    await reglas.agregar(_regla(_config(3), creada=datetime(2026, 10, 2, tzinfo=UTC)))
    agenda = await ConsultarAgendaDeNotificacion(reglas).ejecutar(empresa_id=EMPRESA)
    assert agenda.anticipaciones_min == (3 * 60,)


# --------------------------------------------------------------------- fila corrupta (D-U8-5)


@pytest.mark.asyncio
async def test_una_fila_mal_formada_levanta_agenda_mal_formada_con_el_id_de_la_regla() -> None:
    """Quien barre (el recordatorio de turno) la distingue por el tipo y por el `regla_id`."""
    reglas = ReglasFalsas()
    corrupta = _regla(_config(24))
    corrupta.configuracion = {"recordatorios": "no es una lista"}
    await reglas.agregar(corrupta)

    with pytest.raises(AgendaMalFormada) as exc:
        await ConsultarAgendaDeNotificacion(reglas).ejecutar(empresa_id=EMPRESA)

    assert exc.value.regla_id == corrupta.id
    assert isinstance(exc.value, EntradaInvalida)
    assert "no es una lista" not in str(exc.value)


# --------------------------------------------------------------------- el formulario


def test_el_formulario_se_traduce_y_la_validacion_es_del_dominio() -> None:
    configuracion = configuracion_de_agenda_desde(
        {"recordatorios": [{"horas_antes": 2}, {"horas_antes": 24}]}
    )
    assert configuracion == _config(24, 2)

    with pytest.raises(EntradaInvalida):
        configuracion_de_agenda_desde({"recordatorios": []})
