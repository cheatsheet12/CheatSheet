"""HS-T2 RN-04 / HU-E11-01 — configurar y consultar el horario de atención (casos 12 a 15)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.business_config.application.atencion import (
    ConfigurarHorarioDeAtencion,
    ConsultarAtencion,
    configuracion_de_atencion_desde,
)
from cheatsheet.contexts.business_config.application.reglas import MOTIVO_SOLO_ADMIN
from cheatsheet.contexts.business_config.domain.horario_de_atencion import (
    MENSAJE_CIERRE_ANTES_QUE_APERTURA,
    ConfiguracionDeAtencion,
    FranjaDeAtencion,
    PoliticaFueraDeHorario,
)
from cheatsheet.contexts.business_config.domain.horario_de_atencion_json import como_json
from cheatsheet.contexts.business_config.domain.regla import ReglaDeNegocio, TipoRegla
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, OperacionNoPermitida
from cheatsheet.shared.events import EventoDeDominio
from cheatsheet.shared.roles import RolUsuario
from cheatsheet.shared.zona_horaria import ZONA_ARGENTINA

EMPRESA = EmpresaId(uuid4())
USUARIO = UsuarioId(uuid4())
#: Lunes 05/10/2026 22:00 en Argentina.
AHORA = datetime(2026, 10, 5, 22, 0, tzinfo=ZONA_ARGENTINA)


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


def _config(
    *fechas: date, politica: PoliticaFueraDeHorario = PoliticaFueraDeHorario.AGENTE_RESPONDE
) -> ConfiguracionDeAtencion:
    return ConfiguracionDeAtencion(
        dias={dia: (FranjaDeAtencion.desde_textos("09:00", "19:00"),) for dia in range(5)},
        fechas_cerradas=frozenset(fechas),
        politica=politica,
    )


def _guardar(
    reglas: ReglasFalsas,
    publicador: PublicadorFalso,
    configuracion: ConfiguracionDeAtencion,
    *,
    rol: RolUsuario = RolUsuario.ADMINISTRADOR,
    prioridad: int = 0,
) -> Any:
    return ConfigurarHorarioDeAtencion(reglas=reglas, publicador=publicador).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=rol,
        configuracion=configuracion,
        ahora=AHORA,
        prioridad=prioridad,
    )


def _regla(
    configuracion: ConfiguracionDeAtencion,
    *,
    prioridad: int = 0,
    activa: bool = True,
    creada: datetime = datetime(2026, 10, 1, tzinfo=UTC),
) -> ReglaDeNegocio:
    return ReglaDeNegocio(
        id=uuid4(),
        empresa_id=EMPRESA,
        tipo=TipoRegla.HORARIO_DE_ATENCION,
        configuracion=como_json(configuracion),
        created_at=creada,
        prioridad=prioridad,
        activa=activa,
    )


# --------------------------------------------------------------------- caso 12


@pytest.mark.asyncio
async def test_crea_la_regla_y_un_segundo_guardado_la_reemplaza() -> None:
    reglas, publicador = ReglasFalsas(), PublicadorFalso()

    primera = await _guardar(reglas, publicador, _config())
    segunda = await _guardar(
        reglas, publicador, _config(politica=PoliticaFueraDeHorario.MENSAJE_FIJO), prioridad=2
    )

    assert primera.id == segunda.id
    assert len(reglas.guardadas) == 1
    assert segunda.tipo is TipoRegla.HORARIO_DE_ATENCION
    assert segunda.configuracion["politica"] == "MENSAJE_FIJO"
    assert segunda.prioridad == 2
    assert [evento.accion for evento in publicador.eventos] == [  # type: ignore[attr-defined]
        "alta_regla_de_horario_de_atencion",
        "editar_regla_de_horario_de_atencion",
    ]


@pytest.mark.asyncio
async def test_guardar_una_regla_desactivada_la_reactiva() -> None:
    reglas, publicador = ReglasFalsas(), PublicadorFalso()
    regla = _regla(_config(), activa=False)
    await reglas.agregar(regla)

    guardada = await _guardar(reglas, publicador, _config())

    assert guardada.id == regla.id
    assert guardada.activa is True


@pytest.mark.asyncio
async def test_al_guardar_descarta_las_fechas_anteriores_a_un_horizonte_y_conserva_el_resto() -> (
    None
):
    reglas, publicador = ReglasFalsas(), PublicadorFalso()
    muy_vieja = date(2025, 10, 3)  # hoy - 367 días
    limite = date(2025, 10, 4)  # hoy - 366 días: todavía puede importar
    ayer = date(2026, 10, 4)
    futura = date(2027, 1, 1)

    regla = await _guardar(reglas, publicador, _config(muy_vieja, limite, ayer, futura))

    assert regla.configuracion["fechas_cerradas"] == ["2025-10-04", "2026-10-04", "2027-01-01"]


# --------------------------------------------------------------------- caso 13


@pytest.mark.asyncio
async def test_un_operador_no_puede_configurar_el_horario() -> None:
    reglas, publicador = ReglasFalsas(), PublicadorFalso()

    with pytest.raises(OperacionNoPermitida) as exc:
        await _guardar(reglas, publicador, _config(), rol=RolUsuario.OPERADOR)

    assert str(exc.value) == MOTIVO_SOLO_ADMIN
    assert reglas.guardadas == {}


# --------------------------------------------------------------------- caso 14


@pytest.mark.asyncio
async def test_sin_regla_la_empresa_esta_siempre_abierta() -> None:
    estado = await ConsultarAtencion(ReglasFalsas()).ejecutar(empresa_id=EMPRESA, ahora=AHORA)

    assert estado.configurado is False
    assert estado.abierto is True


@pytest.mark.asyncio
async def test_una_regla_desactivada_deja_de_aplicarse_de_inmediato() -> None:
    reglas = ReglasFalsas()
    await reglas.agregar(_regla(_config(), activa=False))

    estado = await ConsultarAtencion(reglas).ejecutar(empresa_id=EMPRESA, ahora=AHORA)

    assert estado.configurado is False
    assert estado.abierto is True


@pytest.mark.asyncio
async def test_con_regla_devuelve_el_estado_calculado_para_ahora() -> None:
    reglas = ReglasFalsas()
    await reglas.agregar(_regla(_config(politica=PoliticaFueraDeHorario.MENSAJE_FIJO)))

    estado = await ConsultarAtencion(reglas).ejecutar(empresa_id=EMPRESA, ahora=AHORA)

    assert estado.configurado is True
    assert estado.abierto is False
    assert estado.politica is PoliticaFueraDeHorario.MENSAJE_FIJO
    assert estado.proxima_apertura == datetime(2026, 10, 6, 9, 0, tzinfo=ZONA_ARGENTINA)
    assert estado.cerrado_desde == datetime(2026, 10, 5, 19, 0, tzinfo=ZONA_ARGENTINA)


@pytest.mark.asyncio
async def test_sin_apertura_en_el_horizonte_la_proxima_apertura_es_none() -> None:
    reglas = ReglasFalsas()
    solo_lunes = ConfiguracionDeAtencion(
        dias={0: (FranjaDeAtencion.desde_textos("09:00", "19:00"),)},
        fechas_cerradas=frozenset(
            date.fromordinal(date(2026, 10, 12).toordinal() + 7 * n) for n in range(53)
        ),
    )
    await reglas.agregar(_regla(solo_lunes))

    estado = await ConsultarAtencion(reglas).ejecutar(empresa_id=EMPRESA, ahora=AHORA)

    assert estado.abierto is False
    assert estado.proxima_apertura is None


@pytest.mark.asyncio
async def test_la_consulta_usa_la_hora_argentina_aunque_ahora_llegue_en_utc() -> None:
    reglas = ReglasFalsas()
    await reglas.agregar(_regla(_config()))
    utc = datetime(2026, 10, 5, 13, 0, tzinfo=UTC)  # lunes 10:00 en Argentina

    estado = await ConsultarAtencion(reglas).ejecutar(empresa_id=EMPRESA, ahora=utc)

    assert estado.abierto is True
    assert utc.astimezone(ZONA_ARGENTINA).hour == 10


# --------------------------------------------------------------------- caso 15


@pytest.mark.asyncio
async def test_con_dos_reglas_rige_la_de_mayor_prioridad_y_a_igualdad_la_mas_reciente() -> None:
    reglas = ReglasFalsas()
    await reglas.agregar(_regla(_config(), prioridad=1))
    await reglas.agregar(_regla(_config(politica=PoliticaFueraDeHorario.MENSAJE_FIJO), prioridad=5))
    estado = await ConsultarAtencion(reglas).ejecutar(empresa_id=EMPRESA, ahora=AHORA)
    assert estado.politica is PoliticaFueraDeHorario.MENSAJE_FIJO

    reglas = ReglasFalsas()
    await reglas.agregar(_regla(_config(), creada=datetime(2026, 10, 1, tzinfo=UTC)))
    await reglas.agregar(
        _regla(
            _config(politica=PoliticaFueraDeHorario.MENSAJE_FIJO),
            creada=datetime(2026, 10, 2, tzinfo=UTC),
        )
    )
    estado = await ConsultarAtencion(reglas).ejecutar(empresa_id=EMPRESA, ahora=AHORA)
    assert estado.politica is PoliticaFueraDeHorario.MENSAJE_FIJO


# --------------------------------------------------------------------- el formulario


def test_el_formulario_se_traduce_y_la_validacion_es_del_dominio() -> None:
    configuracion = configuracion_de_atencion_desde(
        {
            "politica": "MENSAJE_FIJO",
            "dias": [{"dia": 0, "franjas": [{"desde": "09:00", "hasta": "13:00"}]}],
            "fechas_cerradas": ["2026-10-12"],
        }
    )
    assert configuracion.politica is PoliticaFueraDeHorario.MENSAJE_FIJO
    assert configuracion.fechas_cerradas == frozenset({date(2026, 10, 12)})

    with pytest.raises(EntradaInvalida) as exc:
        configuracion_de_atencion_desde(
            {
                "politica": "AGENTE_RESPONDE",
                "dias": [{"dia": 0, "franjas": [{"desde": "13:00", "hasta": "09:00"}]}],
                "fechas_cerradas": [],
            }
        )
    assert str(exc.value) == MENSAJE_CIERRE_ANTES_QUE_APERTURA
