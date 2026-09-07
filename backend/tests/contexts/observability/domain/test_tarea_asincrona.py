"""The state machine of `TareaAsincrona` (HS-T6).

These tests are about what the aggregate **refuses**. The happy path is three lines; the
value is in case 4, where an illegal transition has to raise rather than quietly leave a
task in a state nothing will ever pick up again.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cheatsheet.contexts.observability.domain.tarea_asincrona import (
    MAX_LONGITUD_RESULTADO,
    EstadoTarea,
    TareaAsincrona,
)
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada
from cheatsheet.shared.idempotencia import ClaveDeIdempotencia

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())


def _tarea(**overrides: object) -> TareaAsincrona:
    base: dict[str, object] = {
        "id": uuid4(),
        "empresa_id": EMPRESA,
        "tipo": "spreadsheet_sync.procesar_planilla",
        "clave_idempotencia": ClaveDeIdempotencia("empresa:tipo:huella"),
        "created_at": AHORA,
        "updated_at": AHORA,
    }
    base.update(overrides)
    return TareaAsincrona(**base)  # type: ignore[arg-type]


def test_una_tarea_nace_pendiente_y_sin_intentos() -> None:
    tarea = _tarea()
    assert tarea.estado is EstadoTarea.PENDIENTE
    assert tarea.intentos == 0
    assert not tarea.es_terminal


def test_reclamar_la_tarea_cuenta_el_intento() -> None:
    """RN-01: the attempt is counted when it starts, not when it fails.

    A worker that dies mid-task never reports anything. Counting on start makes that
    crash cost an attempt, which is the conservative direction — the task eventually
    reaches the DLQ instead of looping forever.
    """
    tarea = _tarea()
    tarea.marcar_en_curso(ahora=AHORA)

    assert tarea.estado is EstadoTarea.EN_CURSO
    assert tarea.intentos == 1


def test_un_fallo_con_intentos_disponibles_la_deja_reintentable() -> None:
    """Caso 1 del plan — RN-01."""
    tarea = _tarea()
    tarea.marcar_en_curso(ahora=AHORA)
    tarea.marcar_fallida(motivo="ARCA no respondio", ahora=AHORA)

    assert tarea.estado is EstadoTarea.FALLIDA
    assert not tarea.es_terminal
    assert not tarea.agoto_los_intentos(max_intentos=5)
    assert tarea.resultado == "ARCA no respondio"


def test_una_tarea_que_agota_el_maximo_puede_derivarse() -> None:
    """Caso 2 del plan — RN-02."""
    tarea = _tarea()
    for _ in range(3):
        tarea.marcar_en_curso(ahora=AHORA)
        tarea.marcar_fallida(motivo="timeout", ahora=AHORA)

    assert tarea.agoto_los_intentos(max_intentos=3)

    tarea.derivar_a_dlq(ahora=AHORA)
    assert tarea.estado is EstadoTarea.DLQ
    assert tarea.fue_derivada
    assert tarea.es_terminal


#: Each case is the transition itself, as a callable, so the `pytest.raises` block below
#: holds one statement and nothing else -- the branching that used to live inside it was
#: deciding *what* to test where the test should only be running it.
TRANSICIONES_ILEGALES: list[tuple[str, EstadoTarea, Callable[[TareaAsincrona], None]]] = [
    ("completada -> dlq", EstadoTarea.COMPLETADA, lambda t: t.derivar_a_dlq(ahora=AHORA)),
    ("completada -> en curso", EstadoTarea.COMPLETADA, lambda t: t.marcar_en_curso(ahora=AHORA)),
    ("dlq -> en curso", EstadoTarea.DLQ, lambda t: t.marcar_en_curso(ahora=AHORA)),
    ("dlq -> dlq", EstadoTarea.DLQ, lambda t: t.derivar_a_dlq(ahora=AHORA)),
    ("pendiente -> dlq", EstadoTarea.PENDIENTE, lambda t: t.derivar_a_dlq(ahora=AHORA)),
    ("pendiente -> completada", EstadoTarea.PENDIENTE, lambda t: t.marcar_completada(ahora=AHORA)),
    ("en curso -> en curso", EstadoTarea.EN_CURSO, lambda t: t.marcar_en_curso(ahora=AHORA)),
    (
        "completada -> fallida",
        EstadoTarea.COMPLETADA,
        lambda t: t.marcar_fallida(motivo="x", ahora=AHORA),
    ),
]


@pytest.mark.parametrize(
    ("estado_inicial", "transicion"),
    [(estado, fn) for _, estado, fn in TRANSICIONES_ILEGALES],
    ids=[nombre for nombre, _, _ in TRANSICIONES_ILEGALES],
)
def test_una_transicion_ilegal_es_rechazada(
    estado_inicial: EstadoTarea, transicion: Callable[[TareaAsincrona], None]
) -> None:
    """Caso 4 del plan.

    `DLQ → DLQ` being illegal is not pedantry: it is exactly what makes the Beat sweep
    idempotent without a claim in Redis. A second run over the same rows moves nothing
    because the aggregate says no.
    """
    tarea = _tarea(estado=estado_inicial)

    with pytest.raises(InvarianteViolada):
        transicion(tarea)


def test_el_motivo_del_fallo_se_recorta_y_nunca_guarda_el_payload() -> None:
    """Caso 8 del plan.

    A traceback is not a business fact, and `resultado` is read by a human deciding
    whether to replay. The cap also keeps a runaway error message from turning the row
    into the thing that fills the disk.
    """
    tarea = _tarea(payload={"cuit": "20123456786", "telefono": "+5493511234567"})
    tarea.marcar_en_curso(ahora=AHORA)
    tarea.marcar_fallida(motivo="x" * (MAX_LONGITUD_RESULTADO + 500), ahora=AHORA)

    assert tarea.resultado is not None
    assert len(tarea.resultado) == MAX_LONGITUD_RESULTADO
    # The payload stays in its own column and never leaks into the human-read one.
    assert "20123456786" not in tarea.resultado


def test_completar_limpia_el_motivo_de_un_intento_anterior() -> None:
    """A task that failed once and then succeeded must not keep advertising the failure."""
    tarea = _tarea()
    tarea.marcar_en_curso(ahora=AHORA)
    tarea.marcar_fallida(motivo="conexion rechazada", ahora=AHORA)
    tarea.marcar_en_curso(ahora=AHORA + timedelta(minutes=1))
    tarea.marcar_completada(ahora=AHORA + timedelta(minutes=2))

    assert tarea.estado is EstadoTarea.COMPLETADA
    assert tarea.resultado is None
    assert tarea.intentos == 2


def test_un_motivo_vacio_es_rechazado() -> None:
    tarea = _tarea()
    tarea.marcar_en_curso(ahora=AHORA)

    with pytest.raises(EntradaInvalida):
        tarea.marcar_fallida(motivo="   ", ahora=AHORA)


def test_un_tipo_vacio_es_rechazado() -> None:
    with pytest.raises(EntradaInvalida):
        _tarea(tipo="  ")


def test_una_marca_de_tiempo_sin_zona_es_rechazada() -> None:
    with pytest.raises(EntradaInvalida):
        _tarea(created_at=datetime(2026, 9, 7, 12, 0))  # noqa: DTZ001 — that is the point


def test_el_maximo_de_intentos_tiene_que_ser_positivo() -> None:
    with pytest.raises(EntradaInvalida):
        _tarea().agoto_los_intentos(max_intentos=0)
