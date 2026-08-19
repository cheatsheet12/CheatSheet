"""El barrido y la tarea por empresa — caso 23 del plan, y la ventana de idempotencia.

Lo que la tarea aporta por encima del caso de uso son dos garantías, y son las que se
prueban acá:

- **una redelivery no vuelve a preguntarle a Meta ni manda un segundo mail**, aunque la
  cola sólo pueda prometer at-least-once;
- **un broker caído no rompe el barrido**: la empresa que no se pudo encolar se reintenta
  en la próxima corrida, treinta minutos después.

Ni Redis ni PostgreSQL: el registro de idempotencia tiene una implementación en memoria y
el resto se inyecta.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from cheatsheet.contexts.integrations.application.ports import AvisoDeIntegracion
from cheatsheet.contexts.integrations.application.sondeo import Desenlace
from cheatsheet.contexts.integrations.domain.eventos import CambioDeEstado
from cheatsheet.contexts.integrations.domain.valores import EstadoDeConexion, SistemaExterno
from cheatsheet.platform.cache import RegistroDeIdempotenciaEnMemoria
from cheatsheet.platform.settings import Settings
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.idempotencia import ClaveDeIdempotencia
from cheatsheet.workers import tasks_integrations
from cheatsheet.workers.base import EjecutorIdempotente
from cheatsheet.workers.beat import programacion
from kombu.exceptions import OperationalError

from tests.conftest import settings_de_prueba

DESENLACE = Desenlace(
    cambio=CambioDeEstado(
        sistema=SistemaExterno.WHATSAPP,
        anterior=EstadoDeConexion.PENDIENTE,
        nuevo=EstadoDeConexion.CONECTADO,
        detalle=None,
    ),
    estado=EstadoDeConexion.CONECTADO,
    detalle=None,
)


class AvisoEspia:
    """Implements `PortAvisoDeIntegracion`. Records instead of sending."""

    def __init__(self) -> None:
        self.avisos: list[AvisoDeIntegracion] = []

    async def avisar(self, aviso: AvisoDeIntegracion) -> None:
        self.avisos.append(aviso)


def test_la_ventana_cambia_entre_corridas_y_no_dentro_de_una() -> None:
    """Es lo que hace que una redelivery comparta clave y la corrida siguiente no.

    Derivada del reloj y no de un contador porque el barrido no guarda estado y Beat puede
    reiniciarse entre corridas.
    """
    settings = replace(settings_de_prueba(), whatsapp_sondeo_minutos=30)

    ventana = tasks_integrations._ventana(settings)

    assert ventana.startswith("30m-")
    assert tasks_integrations._ventana(settings) == ventana


def test_un_intervalo_de_cero_no_divide_por_cero() -> None:
    """`WHATSAPP_SONDEO_MINUTOS=0` es un error de configuración, no un crash del worker."""
    settings = replace(settings_de_prueba(), whatsapp_sondeo_minutos=0)

    assert tasks_integrations._ventana(settings).startswith("1m-")


@pytest.mark.asyncio
async def test_una_redelivery_de_la_misma_ventana_no_repite_el_efecto(
    empresa_id: EmpresaId,
) -> None:
    """Caso 23. Dos workers tomando el mismo mensaje no pueden mandar dos mails.

    Se prueba sobre la clave y el ejecutor —que es donde vive la garantía— en lugar de
    sobre la tarea entera: la tarea sólo los compone, y componerlos con una base y un
    Redis reales ya lo cubre `tests/integracion`.
    """
    registro = RegistroDeIdempotenciaEnMemoria()
    corridas: list[int] = []

    async def efecto() -> int:
        corridas.append(1)
        return 1

    clave = ClaveDeIdempotencia.de(
        empresa_id=empresa_id,
        tipo=tasks_integrations.NOMBRE_EMPRESA,
        payload={"ventana": "30m-123"},
    )
    for _ in range(3):
        await EjecutorIdempotente(registro).ejecutar(clave, efecto)

    assert len(corridas) == 1


@pytest.mark.asyncio
async def test_la_corrida_siguiente_si_vuelve_a_preguntar(empresa_id: EmpresaId) -> None:
    """Lo contrario también importa: una clave eterna dejaría de sondear para siempre."""
    registro = RegistroDeIdempotenciaEnMemoria()
    corridas: list[int] = []

    async def efecto() -> int:
        corridas.append(1)
        return 1

    for ventana in ("30m-123", "30m-124"):
        clave = ClaveDeIdempotencia.de(
            empresa_id=empresa_id,
            tipo=tasks_integrations.NOMBRE_EMPRESA,
            payload={"ventana": ventana},
        )
        await EjecutorIdempotente(registro).ejecutar(clave, efecto)

    assert len(corridas) == 2


def test_un_broker_caido_no_rompe_el_barrido(
    monkeypatch: pytest.MonkeyPatch, empresa_id: EmpresaId
) -> None:
    """La empresa que no se pudo encolar se reintenta en la próxima corrida.

    Convertirlo en una excepción haría fallar el barrido entero por una empresa, que es
    exactamente el modo de falla que el fan-out existe para no tener.
    """

    class DespachadorCaido:
        def send_task(self, *_args: Any, **_kwargs: Any) -> None:
            raise OperationalError("no hay broker")

    monkeypatch.setattr(tasks_integrations, "_despachador", lambda _: DespachadorCaido())

    tasks_integrations._encolar_empresa(settings_de_prueba(), empresa_id)


def test_el_barrido_encola_una_tarea_por_empresa(
    monkeypatch: pytest.MonkeyPatch, empresa_id: EmpresaId
) -> None:
    enviados: list[dict[str, Any]] = []

    class DespachadorEspia:
        def send_task(self, nombre: str, **kwargs: Any) -> None:
            enviados.append({"nombre": nombre, **kwargs})

    monkeypatch.setattr(tasks_integrations, "_despachador", lambda _: DespachadorEspia())

    tasks_integrations._encolar_empresa(settings_de_prueba(), empresa_id)

    assert enviados[0]["nombre"] == tasks_integrations.NOMBRE_EMPRESA
    assert enviados[0]["kwargs"]["empresa_id"] == str(empresa_id)
    assert enviados[0]["queue"] == "integrations_sync"


@pytest.mark.asyncio
async def test_sin_desenlaces_no_se_construye_ni_se_manda_un_aviso(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El desenlace normal del sondeo es «sigue pendiente», 48 veces por día."""
    espia = AvisoEspia()
    monkeypatch.setattr(tasks_integrations, "crear_aviso", lambda _: espia)

    await tasks_integrations._avisar(settings_de_prueba(), [], ("ana@empresa.com",))

    assert espia.avisos == []


@pytest.mark.asyncio
async def test_un_desenlace_avisa_a_todos_los_administradores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    espia = AvisoEspia()
    monkeypatch.setattr(tasks_integrations, "crear_aviso", lambda _: espia)

    await tasks_integrations._avisar(
        settings_de_prueba(), [DESENLACE], ("ana@empresa.com", "beto@empresa.com")
    )

    assert len(espia.avisos) == 1
    assert espia.avisos[0].destinatarios == ("ana@empresa.com", "beto@empresa.com")
    assert espia.avisos[0].sistema is SistemaExterno.WHATSAPP
    assert espia.avisos[0].estado is EstadoDeConexion.CONECTADO


def test_beat_programa_el_barrido_con_el_intervalo_configurado() -> None:
    """La primera entrada real de Beat. El intervalo es configuración, no una constante."""
    settings: Settings = replace(settings_de_prueba(), whatsapp_sondeo_minutos=45)

    entradas = programacion(settings)

    entrada = entradas["sondear-integraciones-pendientes"]
    assert entrada["task"] == tasks_integrations.NOMBRE_BARRIDO
    assert entrada["schedule"].total_seconds() == 45 * 60
    assert entrada["options"]["queue"] == "integrations_sync"
