"""`RecordatorioPorWhatsApp` — el recordatorio de turno por WhatsApp (U8, D-U8-9, casos 1, 21, 28, 32).

1. `preparar`: sin teléfono → `SinTelefono`; con la plantilla aprobada → sale como plantilla con sus
   cuatro variables (la fecha y la hora en la zona de la agenda); sin ella → texto de fábrica.
2. `mandar` **nunca levanta** y propaga si la falla es transitoria (caso 28).
3. Ningún log lleva el nombre, el teléfono ni el texto (caso 32).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.scheduling.application.ports import ServicioAgendable
from cheatsheet.contexts.scheduling.application.ports_de_recordatorios import (
    RecordatorioListo,
    SinTelefono,
)
from cheatsheet.contexts.scheduling.domain.turno import Franja, Turno
from cheatsheet.contexts.scheduling.infrastructure import recordatorio_por_whatsapp
from cheatsheet.contexts.scheduling.infrastructure.avisos import ResultadoLocal
from cheatsheet.contexts.scheduling.infrastructure.recordatorio_por_whatsapp import (
    CODIGO_RECORDATORIO,
    RecordatorioPorWhatsApp,
)
from cheatsheet.shared.empresa import EmpresaId
from structlog.testing import capture_logs

from tests.logs import logger_nuevo

from .canal_de_avisos_falso import CanalDeAvisosFalso

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _logger(monkeypatch: pytest.MonkeyPatch) -> None:
    logger_nuevo(monkeypatch, recordatorio_por_whatsapp)


TELEFONO = "5491112345678"
NOMBRE = "Ana Diaz"
#: 15/10/2026 00:30 en la Argentina = 03:30Z: el día en UTC y el argentino coinciden, la hora no.
INICIO = datetime(2026, 10, 15, 13, 0, tzinfo=UTC)
SERVICIO = ServicioAgendable(id=uuid4(), nombre="Corte", duracion_estandar_min=30)


def _turno(inicio: datetime = INICIO) -> Turno:
    return Turno(
        id=uuid4(),
        empresa_id=EmpresaId(uuid4()),
        cliente_id=uuid4(),
        servicio_id=SERVICIO.id,
        recurso_id=uuid4(),
        franja=Franja(inicio=inicio, duracion_min=30),
        created_at=inicio,
    )


class _Clientes:
    def __init__(self, contacto: tuple[str, str] | None = (NOMBRE, TELEFONO)) -> None:
        self._contacto = contacto

    async def contacto_de(self, cliente_id: UUID) -> tuple[str, str] | None:
        del cliente_id
        return self._contacto


class _Servicios:
    def __init__(self, servicio: ServicioAgendable | None = SERVICIO) -> None:
        self._servicio = servicio

    async def buscar_agendable(self, servicio_id: UUID) -> ServicioAgendable | None:
        del servicio_id
        return self._servicio

    async def listar_agendables(self) -> list[ServicioAgendable]:
        return []


@dataclass(frozen=True)
class _Aprobada:
    nombre_en_meta: str
    idioma: str
    parametros: Mapping[str, str]
    texto: str


class _Plantillas:
    def __init__(self, aprobada: bool) -> None:
        self.pedidas: list[tuple[str, dict[str, str]]] = []
        self._aprobada = aprobada

    async def para(self, codigo: str, variables: Mapping[str, str]) -> _Aprobada | None:
        self.pedidas.append((codigo, dict(variables)))
        if not self._aprobada:
            return None
        return _Aprobada(
            nombre_en_meta="recordatorio_de_turno",
            idioma="es_AR",
            parametros={k: variables[k] for k in ("nombre", "servicio", "fecha", "hora")},
            texto="Hola Ana Diaz, te recordamos tu turno de Corte el 15/10/2026 a las 10:00.",
        )


def _adaptador(
    *,
    canal: CanalDeAvisosFalso | None = None,
    plantillas: _Plantillas | None = None,
    clientes: _Clientes | None = None,
    servicios: _Servicios | None = None,
) -> tuple[RecordatorioPorWhatsApp, CanalDeAvisosFalso, _Plantillas]:
    canal = canal or CanalDeAvisosFalso()
    plantillas = plantillas or _Plantillas(aprobada=False)
    return (
        RecordatorioPorWhatsApp(
            clientes=clientes or _Clientes(),
            servicios=servicios or _Servicios(),
            canal=canal,
            plantillas=plantillas,
        ),
        canal,
        plantillas,
    )


class TestPreparar:
    async def test_sin_telefono_devuelve_sin_telefono(self) -> None:
        adaptador, canal, _ = _adaptador(clientes=_Clientes(contacto=None))

        preparado = await adaptador.preparar(_turno(), 24 * 60)

        assert isinstance(preparado, SinTelefono)
        assert canal.notificaciones == []

    async def test_sin_plantilla_aprobada_sale_el_texto_de_fabrica_en_hora_argentina(self) -> None:
        adaptador, _, _ = _adaptador()

        preparado = await adaptador.preparar(_turno(), 24 * 60)

        assert isinstance(preparado, RecordatorioListo)
        assert preparado.plantilla is None
        assert preparado.texto == (
            "Hola Ana Diaz, te recordamos tu turno de Corte el 15/10/2026 a las 10:00."
        )
        assert preparado.telefono == TELEFONO

    async def test_con_la_plantilla_aprobada_sale_como_plantilla_con_sus_cuatro_variables(
        self,
    ) -> None:
        adaptador, _, plantillas = _adaptador(plantillas=_Plantillas(aprobada=True))

        preparado = await adaptador.preparar(_turno(), 24 * 60)

        assert isinstance(preparado, RecordatorioListo)
        assert preparado.plantilla is not None
        assert preparado.plantilla.nombre == "recordatorio_de_turno"
        assert dict(preparado.plantilla.parametros) == {
            "nombre": NOMBRE,
            "servicio": "Corte",
            "fecha": "15/10/2026",
            "hora": "10:00",
        }
        assert plantillas.pedidas[0][0] == CODIGO_RECORDATORIO

    async def test_a_las_00_30_argentinas_la_fecha_es_la_del_dia_argentino(self) -> None:
        """**Caso 12.** 00:30 AR del 16/10 son las 03:30Z del 16/10; 22:00 AR del 15 son 01:00Z del 16."""
        adaptador, _, _ = _adaptador()
        noche = datetime(2026, 10, 16, 1, 0, tzinfo=UTC)

        preparado = await adaptador.preparar(_turno(noche), 24 * 60)

        assert isinstance(preparado, RecordatorioListo)
        assert "15/10/2026 a las 22:00" in preparado.texto

    async def test_un_servicio_que_ya_no_es_agendable_no_deja_el_aviso_sin_texto(self) -> None:
        adaptador, _, _ = _adaptador(servicios=_Servicios(servicio=None))

        preparado = await adaptador.preparar(_turno(), 24 * 60)

        assert isinstance(preparado, RecordatorioListo)
        assert "el servicio" in preparado.texto

    async def test_el_repr_no_lleva_el_telefono_ni_el_texto(self) -> None:
        adaptador, _, _ = _adaptador(plantillas=_Plantillas(aprobada=True))

        preparado = await adaptador.preparar(_turno(), 24 * 60)

        assert TELEFONO not in repr(preparado)
        assert NOMBRE not in repr(preparado)


class TestMandar:
    async def test_manda_por_el_canal_con_la_plantilla_y_el_cliente_del_turno(self) -> None:
        adaptador, canal, _ = _adaptador(plantillas=_Plantillas(aprobada=True))
        turno = _turno()
        preparado = await adaptador.preparar(turno, 24 * 60)
        assert isinstance(preparado, RecordatorioListo)

        resultado = await adaptador.mandar(preparado)

        assert resultado.enviado is True
        (notificacion,) = canal.notificaciones
        assert notificacion.cliente_id == turno.cliente_id
        assert notificacion.telefono == TELEFONO
        assert notificacion.nombre_de_plantilla == "recordatorio_de_turno"

    @pytest.mark.parametrize("transitoria", [True, False])
    async def test_propaga_el_motivo_y_si_la_falla_es_transitoria(self, transitoria: bool) -> None:
        """**Caso 28** del lado de `scheduling`."""
        canal = CanalDeAvisosFalso(
            resultado=ResultadoLocal(enviado=False, falla="SATURADA", transitoria=transitoria)
        )
        adaptador, _, _ = _adaptador(canal=canal)
        preparado = await adaptador.preparar(_turno(), 24 * 60)
        assert isinstance(preparado, RecordatorioListo)

        resultado = await adaptador.mandar(preparado)

        assert (resultado.enviado, resultado.falla, resultado.transitoria) == (
            False,
            "SATURADA",
            transitoria,
        )

    async def test_un_canal_que_explota_no_levanta_y_queda_como_error(self) -> None:
        adaptador, _, _ = _adaptador(canal=CanalDeAvisosFalso(falla=RuntimeError(TELEFONO)))
        preparado = await adaptador.preparar(_turno(), 24 * 60)
        assert isinstance(preparado, RecordatorioListo)

        with capture_logs() as logs:
            resultado = await adaptador.mandar(preparado)

        assert (resultado.enviado, resultado.falla, resultado.transitoria) == (
            False,
            "ERROR",
            False,
        )
        assert logs == [
            {
                "event": "recordatorio_de_turno_fallido",
                "causa": "RuntimeError",
                "log_level": "warning",
            }
        ]

    async def test_enviado_pero_sin_registrar_cuenta_como_enviado_y_deja_un_log(self) -> None:
        canal = CanalDeAvisosFalso(
            resultado=ResultadoLocal(enviado=True, sin_registrar=True, causa="OperationalError")
        )
        adaptador, _, _ = _adaptador(canal=canal)
        preparado = await adaptador.preparar(_turno(), 24 * 60)
        assert isinstance(preparado, RecordatorioListo)

        with capture_logs() as logs:
            resultado = await adaptador.mandar(preparado)

        assert resultado.enviado is True
        assert [uno["event"] for uno in logs] == ["recordatorio_de_turno_sin_registrar"]

    async def test_ningun_log_lleva_el_nombre_el_telefono_ni_el_texto(self) -> None:
        """**Caso 32.**"""
        canal = CanalDeAvisosFalso(
            resultado=ResultadoLocal(enviado=False, falla="131047", sin_registrar=True, causa="X")
        )
        adaptador, _, _ = _adaptador(canal=canal)

        with capture_logs() as logs:
            preparado = await adaptador.preparar(_turno(), 24 * 60)
            assert isinstance(preparado, RecordatorioListo)
            await adaptador.mandar(preparado)

        volcado = repr(logs)
        assert TELEFONO not in volcado
        assert NOMBRE not in volcado
        assert "te recordamos" not in volcado
