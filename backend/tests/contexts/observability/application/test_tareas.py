"""The use cases of HS-T6 — attempts, results, and the sweep that retires the exhausted.

The fake repository below is deliberately dumb: it stores aggregates by id and answers
`listar_fallidas` from the same dict. What it does **not** do is copy them, so a test that
mutates a task through a use case sees the mutation — which is what the real repository
does too, through the session's identity map.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.observability.application.tareas import (
    ACCION_DERIVACION_A_DLQ,
    DerivarTareasAgotadasADLQ,
    RegistrarIntentoDeTarea,
    RegistrarResultadoDeTarea,
)
from cheatsheet.contexts.observability.domain.tarea_asincrona import EstadoTarea, TareaAsincrona
from cheatsheet.shared.auditoria import Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import InvarianteViolada
from cheatsheet.shared.events import EventoDeDominio
from cheatsheet.shared.idempotencia import ClaveDeIdempotencia

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
TIPO = "spreadsheet_sync.procesar_planilla"


class RepositorioFalso:
    def __init__(self) -> None:
        self.tareas: dict[UUID, TareaAsincrona] = {}

    async def agregar(self, tarea: TareaAsincrona) -> None:
        self.tareas[tarea.id] = tarea

    async def actualizar(self, tarea: TareaAsincrona) -> None:
        self.tareas[tarea.id] = tarea

    async def buscar_por_id(self, tarea_id: UUID) -> TareaAsincrona | None:
        return self.tareas.get(tarea_id)

    async def buscar_por_clave(self, clave: ClaveDeIdempotencia) -> TareaAsincrona | None:
        for tarea in self.tareas.values():
            if tarea.clave_idempotencia == clave:
                return tarea
        return None

    async def listar_fallidas(self, *, limite: int) -> list[TareaAsincrona]:
        fallidas = [t for t in self.tareas.values() if t.estado is EstadoTarea.FALLIDA]
        fallidas.sort(key=lambda t: t.created_at)
        return fallidas[:limite]


class PublicadorFalso:
    def __init__(self) -> None:
        self.eventos: list[EventoDeDominio] = []

    async def publicar(self, evento: EventoDeDominio) -> None:
        self.eventos.append(evento)


@pytest.fixture
def tareas() -> RepositorioFalso:
    return RepositorioFalso()


@pytest.fixture
def publicador() -> PublicadorFalso:
    return PublicadorFalso()


def _clave(sufijo: str) -> ClaveDeIdempotencia:
    return ClaveDeIdempotencia.de(empresa_id=EMPRESA, tipo=TIPO, payload={"n": sufijo})


async def _tarea_fallida(
    tareas: RepositorioFalso, *, intentos: int, sufijo: str = "1"
) -> TareaAsincrona:
    """A task that has failed `intentos` times and is waiting for the next attempt."""
    registrar = RegistrarIntentoDeTarea(tareas)
    resultados = RegistrarResultadoDeTarea(tareas)
    tarea = await registrar.ejecutar(
        empresa_id=EMPRESA, tipo=TIPO, clave=_clave(sufijo), ahora=AHORA
    )
    await resultados.fallar(tarea_id=tarea.id, motivo="timeout", ahora=AHORA)
    for _ in range(intentos - 1):
        await registrar.ejecutar(empresa_id=EMPRESA, tipo=TIPO, clave=_clave(sufijo), ahora=AHORA)
        await resultados.fallar(tarea_id=tarea.id, motivo="timeout", ahora=AHORA)
    return tarea


async def test_el_primer_intento_crea_la_tarea_y_la_reclama(tareas: RepositorioFalso) -> None:
    tarea = await RegistrarIntentoDeTarea(tareas).ejecutar(
        empresa_id=EMPRESA, tipo=TIPO, clave=_clave("1"), ahora=AHORA, payload={"archivo": "a.xlsx"}
    )

    assert tarea.estado is EstadoTarea.EN_CURSO
    assert tarea.intentos == 1
    assert tarea.payload == {"archivo": "a.xlsx"}
    assert tareas.tareas[tarea.id] is tarea


async def test_un_reintento_reusa_la_tarea_de_la_misma_clave(tareas: RepositorioFalso) -> None:
    """ADR-009: the key identifies the intended effect, so a retry is the same row."""
    registrar = RegistrarIntentoDeTarea(tareas)
    primera = await registrar.ejecutar(
        empresa_id=EMPRESA, tipo=TIPO, clave=_clave("1"), ahora=AHORA
    )
    await RegistrarResultadoDeTarea(tareas).fallar(
        tarea_id=primera.id, motivo="timeout", ahora=AHORA
    )
    segunda = await registrar.ejecutar(
        empresa_id=EMPRESA, tipo=TIPO, clave=_clave("1"), ahora=AHORA
    )

    assert segunda.id == primera.id
    assert segunda.intentos == 2
    assert len(tareas.tareas) == 1


async def test_una_tarea_ya_completada_no_se_reintenta(tareas: RepositorioFalso) -> None:
    """A redelivery must not resurrect finished work — that is what the key is for."""
    registrar = RegistrarIntentoDeTarea(tareas)
    tarea = await registrar.ejecutar(empresa_id=EMPRESA, tipo=TIPO, clave=_clave("1"), ahora=AHORA)
    await RegistrarResultadoDeTarea(tareas).completar(tarea_id=tarea.id, ahora=AHORA)

    with pytest.raises(InvarianteViolada):
        await registrar.ejecutar(empresa_id=EMPRESA, tipo=TIPO, clave=_clave("1"), ahora=AHORA)


async def test_registrar_el_resultado_de_una_tarea_inexistente_falla(
    tareas: RepositorioFalso,
) -> None:
    with pytest.raises(InvarianteViolada):
        await RegistrarResultadoDeTarea(tareas).completar(tarea_id=uuid4(), ahora=AHORA)


async def test_el_barrido_deriva_solo_lo_que_agoto_los_intentos(
    tareas: RepositorioFalso, publicador: PublicadorFalso
) -> None:
    """Caso 1 y 2 del plan, juntos: el barrido distingue una cosa de la otra."""
    agotada = await _tarea_fallida(tareas, intentos=3, sufijo="agotada")
    viva = await _tarea_fallida(tareas, intentos=1, sufijo="viva")

    resultado = await DerivarTareasAgotadasADLQ(
        tareas=tareas, publicador=publicador, max_intentos=3
    ).ejecutar(ahora=AHORA)

    assert resultado.revisadas == 2
    assert resultado.derivadas == 1
    assert resultado.quedan_reintentos == 1
    assert tareas.tareas[agotada.id].estado is EstadoTarea.DLQ
    assert tareas.tareas[viva.id].estado is EstadoTarea.FALLIDA


async def test_la_derivacion_publica_el_evento_auditable(
    tareas: RepositorioFalso, publicador: PublicadorFalso
) -> None:
    """Caso 3 del plan — RN-04."""
    tarea = await _tarea_fallida(tareas, intentos=3)

    await DerivarTareasAgotadasADLQ(tareas=tareas, publicador=publicador, max_intentos=3).ejecutar(
        ahora=AHORA
    )

    assert len(publicador.eventos) == 1
    evento = publicador.eventos[0]
    assert evento.accion == ACCION_DERIVACION_A_DLQ  # type: ignore[attr-defined]
    assert evento.modulo is Modulo.OBSERVABILITY  # type: ignore[attr-defined]
    assert evento.resultado is Resultado.ERROR  # type: ignore[attr-defined]
    assert evento.empresa_id == EMPRESA
    # The system acted, not a person: HS-T5 models that as a null initiator.
    assert evento.usuario_id is None  # type: ignore[attr-defined]
    assert str(tarea.id) in evento.entidad_afectada  # type: ignore[attr-defined]


async def test_el_evento_no_lleva_el_payload_de_la_tarea(
    tareas: RepositorioFalso, publicador: PublicadorFalso
) -> None:
    """The payload may carry a CUIT; the audit log is not where those go to be copied."""
    registrar = RegistrarIntentoDeTarea(tareas)
    tarea = await registrar.ejecutar(
        empresa_id=EMPRESA,
        tipo=TIPO,
        clave=_clave("1"),
        ahora=AHORA,
        payload={"cuit": "20123456786"},
    )
    resultados = RegistrarResultadoDeTarea(tareas)
    await resultados.fallar(tarea_id=tarea.id, motivo="timeout", ahora=AHORA)
    for _ in range(2):
        await registrar.ejecutar(empresa_id=EMPRESA, tipo=TIPO, clave=_clave("1"), ahora=AHORA)
        await resultados.fallar(tarea_id=tarea.id, motivo="timeout", ahora=AHORA)

    await DerivarTareasAgotadasADLQ(tareas=tareas, publicador=publicador, max_intentos=3).ejecutar(
        ahora=AHORA
    )

    serializado = repr(publicador.eventos[0])
    assert "20123456786" not in serializado


async def test_el_barrido_corrido_dos_veces_no_deriva_de_nuevo(
    tareas: RepositorioFalso, publicador: PublicadorFalso
) -> None:
    """Caso 6 del plan.

    Idempotent through the aggregate's state machine rather than through a claim in
    Redis, which is strictly better: it survives a Redis flush.
    """
    await _tarea_fallida(tareas, intentos=3)
    barrido = DerivarTareasAgotadasADLQ(tareas=tareas, publicador=publicador, max_intentos=3)

    primera = await barrido.ejecutar(ahora=AHORA)
    segunda = await barrido.ejecutar(ahora=AHORA)

    assert primera.derivadas == 1
    assert segunda.derivadas == 0
    assert len(publicador.eventos) == 1


async def test_una_tarea_en_dlq_no_bloquea_a_las_demas(
    tareas: RepositorioFalso, publicador: PublicadorFalso
) -> None:
    """Caso 5 del plan — RN-03, que es el punto entero de la historia."""
    muerta = await _tarea_fallida(tareas, intentos=3, sufijo="muerta")
    await DerivarTareasAgotadasADLQ(tareas=tareas, publicador=publicador, max_intentos=3).ejecutar(
        ahora=AHORA
    )
    assert tareas.tareas[muerta.id].estado is EstadoTarea.DLQ

    # With the dead one retired, ordinary work keeps flowing through the same repository.
    viva = await RegistrarIntentoDeTarea(tareas).ejecutar(
        empresa_id=EMPRESA, tipo=TIPO, clave=_clave("viva"), ahora=AHORA
    )
    await RegistrarResultadoDeTarea(tareas).completar(tarea_id=viva.id, ahora=AHORA)

    assert tareas.tareas[viva.id].estado is EstadoTarea.COMPLETADA


async def test_el_barrido_respeta_el_limite_del_lote(
    tareas: RepositorioFalso, publicador: PublicadorFalso
) -> None:
    """An incident that fails ten thousand tasks must not make the sweep the casualty."""
    for n in range(5):
        await _tarea_fallida(tareas, intentos=3, sufijo=str(n))

    resultado = await DerivarTareasAgotadasADLQ(
        tareas=tareas, publicador=publicador, max_intentos=3
    ).ejecutar(ahora=AHORA, limite=2)

    assert resultado.revisadas == 2
    assert resultado.derivadas == 2
    en_dlq = [t for t in tareas.tareas.values() if t.estado is EstadoTarea.DLQ]
    assert len(en_dlq) == 2
