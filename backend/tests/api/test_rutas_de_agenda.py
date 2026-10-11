"""La tabla de rutas de la agenda no cambia al partir el router (TODO 22.42).

Los 30 tests de `tests/integracion/test_api_agenda.py` sólo corren contra PostgreSQL, así que
esta es la red local: arma el router sin base y compara (método, ruta, código, modelo de
respuesta) en el orden de registro. El orden importa: `GET /turnos/disponibilidad` tiene que
estar antes que `GET /turnos/{turno_id}`, o «disponibilidad» se toma como un `turno_id` y la
ruta contesta 422.
"""

from __future__ import annotations

from typing import cast

from cheatsheet.api.dependencies import Recursos
from cheatsheet.api.routers.agenda import crear_router
from fastapi.routing import APIRoute

_ESPERADAS: list[tuple[str, str, int | None, str]] = [
    ("GET", "/recursos", None, "ListadoDeRecursos"),
    ("GET", "/recursos/servicios", None, "list"),
    ("POST", "/recursos", 201, "RecursoSalida"),
    ("PUT", "/recursos/{recurso_id}/disponibilidad", None, "RecursoSalida"),
    ("PUT", "/recursos/{recurso_id}/servicios", None, "RecursoSalida"),
    ("PUT", "/recursos/{recurso_id}/estado", None, "RecursoSalida"),
    ("POST", "/recursos/{recurso_id}/excepciones", 201, "RecursoSalida"),
    ("DELETE", "/recursos/{recurso_id}/excepciones/{fecha}", None, "RecursoSalida"),
    ("GET", "/turnos", None, "ListadoDeTurnos"),
    ("GET", "/turnos/disponibilidad", None, "DisponibilidadSalida"),
    ("GET", "/turnos/{turno_id}", None, "TurnoSalida"),
    ("POST", "/turnos", 201, "TurnoSalida"),
    ("POST", "/turnos/{turno_id}/cancelacion", None, "TurnoSalida"),
    ("POST", "/turnos/{turno_id}/reprogramacion", None, "TurnoSalida"),
    ("POST", "/turnos/{turno_id}/asistencia", None, "TurnoSalida"),
]


def _rutas() -> list[tuple[str, str, int | None, str]]:
    # Las rutas sólo guardan `recursos` en sus cierres: armar el router no lo toca.
    router = crear_router(cast(Recursos, None))
    tabla: list[tuple[str, str, int | None, str]] = []
    for ruta in router.routes:
        assert isinstance(ruta, APIRoute)
        modelo = getattr(ruta.response_model, "__name__", str(ruta.response_model))
        for metodo in sorted(ruta.methods):
            tabla.append((metodo, ruta.path, ruta.status_code, modelo))
    return tabla


def test_la_tabla_de_rutas_de_la_agenda_no_cambia() -> None:
    assert _rutas() == _ESPERADAS


def test_disponibilidad_se_registra_antes_que_el_turno_por_id() -> None:
    caminos = [(metodo, camino) for metodo, camino, _, _ in _rutas()]
    assert caminos.index(("GET", "/turnos/disponibilidad")) < caminos.index(
        ("GET", "/turnos/{turno_id}")
    )
