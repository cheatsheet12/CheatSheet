"""Los endpoints de la agenda, de punta a punta (HU-E7-01 … HU-E7-06).

La costura que ninguna prueba unitaria mira, y que en esta unidad son dos:

1. **Que el rechazo por solapamiento llegue como 422 con la frase de la historia.** La
   restricción de exclusión vive en PostgreSQL, el repositorio la traduce y `api/errors.py`
   la mapea: tres capas que sólo se prueban juntas desde afuera. Si alguna se desalineara, el
   usuario vería «error del sistema» donde la verdad es «ese horario ya está tomado», y
   volvería a intentar.

2. **Que el rango por defecto sea el día en curso** (HU-E7-01 RN-01). Lo calcula el router,
   así que sólo se ve desde acá.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import pytest_asyncio
from cheatsheet.api.dependencies import Recursos
from cheatsheet.api.main import create_app
from cheatsheet.contexts.scheduling.domain.turno import MENSAJE_HORARIO_OCUPADO
from cheatsheet.platform.settings import Settings

from tests.conftest import settings_de_prueba
from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration]

CONTRASENA = "una-contrasena-larga"

#: Un martes futuro, a las 15 de la zona de la agenda (18 UTC). Futuro para que marcar
#: asistencia esté prohibido salvo cuando el test lo quiera.
MARTES_15 = datetime(2027, 9, 7, 18, 0, tzinfo=UTC)


def _settings() -> Settings:
    return replace(
        settings_de_prueba(),
        database_url=os.environ["DATABASE_URL"],
        database_url_migrations=os.environ["DATABASE_URL_MIGRATIONS"],
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6380/0"),
    )


@pytest_asyncio.fixture
async def cliente_http(esquema_migrado: None) -> AsyncIterator[httpx.AsyncClient]:
    settings = _settings()
    recursos = Recursos.crear(settings)
    app = create_app(settings, recursos)
    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as http:
        yield http
    await recursos.cerrar()


async def _token(http: httpx.AsyncClient, email: str) -> str:
    respuesta = await http.post(
        "/auth/registro",
        json={"email": email, "contrasena": CONTRASENA, "nombre": "Ana Perez"},
    )
    assert respuesta.status_code == 201, respuesta.text
    return str(respuesta.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _servicio(http: httpx.AsyncClient, token: str) -> str:
    respuesta = await http.post(
        "/servicios",
        headers=_auth(token),
        json={
            "nombre": "Corte de pelo",
            "precio": "5000.00",
            "alicuota_iva": "0.21",
            "agendable": True,
            "duracion_estandar_min": 60,
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return str(respuesta.json()["id"])


async def _cliente(http: httpx.AsyncClient, token: str) -> str:
    respuesta = await http.post("/clientes", headers=_auth(token), json={"nombre": "Juan Perez"})
    assert respuesta.status_code == 201, respuesta.text
    return str(respuesta.json()["id"])


async def _recurso(http: httpx.AsyncClient, token: str, servicio_id: str) -> str:
    respuesta = await http.post(
        "/recursos",
        headers=_auth(token),
        json={
            "nombre": "Consultorio 1",
            "tipo": "ESPACIO",
            # Martes 9 a 18, turnos de una hora.
            "patrones": [
                {
                    "dia_semana": 1,
                    "hora_inicio": "09:00:00",
                    "hora_fin": "18:00:00",
                    "duracion_slot_min": 60,
                }
            ],
            "servicios": [servicio_id],
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return str(respuesta.json()["id"])


class Escena:
    def __init__(self, token: str, cliente_id: str, servicio_id: str, recurso_id: str) -> None:
        self.token = token
        self.cliente_id = cliente_id
        self.servicio_id = servicio_id
        self.recurso_id = recurso_id

    def turno(self, inicio: datetime = MARTES_15) -> dict[str, Any]:
        return {
            "cliente_id": self.cliente_id,
            "servicio_id": self.servicio_id,
            "recurso_id": self.recurso_id,
            "inicio": inicio.isoformat(),
        }


async def _escena(http: httpx.AsyncClient, email: str) -> Escena:
    token = await _token(http, email)
    servicio_id = await _servicio(http, token)
    return Escena(
        token, await _cliente(http, token), servicio_id, await _recurso(http, token, servicio_id)
    )


@pytest.mark.asyncio
async def test_reservar_devuelve_201_y_el_turno_aparece_en_la_agenda(
    cliente_http: httpx.AsyncClient,
) -> None:
    escena = await _escena(cliente_http, "agenda-alta@test.local")

    creado = await cliente_http.post("/turnos", headers=_auth(escena.token), json=escena.turno())

    assert creado.status_code == 201, creado.text
    cuerpo = creado.json()
    assert cuerpo["estado"] == "RESERVADO"
    # HU-E7-06 RN-02: lo que distingue este turno de los que va a crear el agente.
    assert cuerpo["canal_reserva"] == "PANEL"
    # La duración sale del servicio, no del formulario.
    assert cuerpo["duracion_min"] == 60
    assert not cuerpo["ya_transcurrio"]

    listado = await cliente_http.get(
        "/turnos",
        headers=_auth(escena.token),
        params={
            "desde": MARTES_15.isoformat(),
            "hasta": (MARTES_15 + timedelta(days=1)).isoformat(),
        },
    )
    assert [uno["id"] for uno in listado.json()["turnos"]] == [cuerpo["id"]]


@pytest.mark.asyncio
async def test_la_franja_ocupada_es_un_422_con_la_frase_de_la_historia(
    cliente_http: httpx.AsyncClient,
) -> None:
    """**Decisión D28** cruzando las tres capas: motor, repositorio y manejador de errores."""
    escena = await _escena(cliente_http, "agenda-ocupada@test.local")
    primero = await cliente_http.post("/turnos", headers=_auth(escena.token), json=escena.turno())
    assert primero.status_code == 201, primero.text

    segundo = await cliente_http.post("/turnos", headers=_auth(escena.token), json=escena.turno())

    assert segundo.status_code == 422, segundo.text
    assert segundo.json()["detalle"] == MENSAJE_HORARIO_OCUPADO


@pytest.mark.asyncio
async def test_la_agenda_sin_rango_muestra_el_dia_en_curso(
    cliente_http: httpx.AsyncClient,
) -> None:
    """HU-E7-01 RN-01. El turno de 2027 existe y **no** sale sin filtro, porque no es hoy."""
    escena = await _escena(cliente_http, "agenda-hoy@test.local")
    creado = await cliente_http.post("/turnos", headers=_auth(escena.token), json=escena.turno())
    assert creado.status_code == 201, creado.text

    hoy = await cliente_http.get("/turnos", headers=_auth(escena.token))

    assert hoy.status_code == 200
    assert hoy.json()["turnos"] == []


@pytest.mark.asyncio
async def test_el_horario_fuera_de_atencion_se_rechaza(
    cliente_http: httpx.AsyncClient,
) -> None:
    escena = await _escena(cliente_http, "agenda-cerrado@test.local")

    # Las 3 de la mañana de la zona de la agenda: el recurso abre a las 9.
    de_madrugada = await cliente_http.post(
        "/turnos",
        headers=_auth(escena.token),
        json=escena.turno(MARTES_15.replace(hour=6)),
    )

    assert de_madrugada.status_code == 422, de_madrugada.text


@pytest.mark.asyncio
async def test_marcar_asistencia_en_un_turno_futuro_se_rechaza(
    cliente_http: httpx.AsyncClient,
) -> None:
    """HU-E7-03, primer criterio, con el 409 que le corresponde a una invariante."""
    escena = await _escena(cliente_http, "agenda-asistencia@test.local")
    creado = await cliente_http.post("/turnos", headers=_auth(escena.token), json=escena.turno())
    turno_id = creado.json()["id"]

    marcado = await cliente_http.post(
        f"/turnos/{turno_id}/asistencia", headers=_auth(escena.token), json={"asistio": True}
    )

    assert marcado.status_code == 409, marcado.text


@pytest.mark.asyncio
async def test_cancelar_y_luego_reservar_la_misma_franja_funciona(
    cliente_http: httpx.AsyncClient,
) -> None:
    """La restricción es parcial: cancelar libera el horario, y el negocio puede revenderlo."""
    escena = await _escena(cliente_http, "agenda-cancelar@test.local")
    creado = await cliente_http.post("/turnos", headers=_auth(escena.token), json=escena.turno())
    turno_id = creado.json()["id"]

    cancelado = await cliente_http.post(
        f"/turnos/{turno_id}/cancelacion", headers=_auth(escena.token)
    )
    assert cancelado.status_code == 200, cancelado.text
    assert cancelado.json()["estado"] == "CANCELADO"

    de_nuevo = await cliente_http.post("/turnos", headers=_auth(escena.token), json=escena.turno())
    assert de_nuevo.status_code == 201, de_nuevo.text


@pytest.mark.asyncio
async def test_reprogramar_conserva_el_estado(cliente_http: httpx.AsyncClient) -> None:
    """HU-E7-02 RN-02, visto desde afuera: el estado que sale es el que entró."""
    escena = await _escena(cliente_http, "agenda-reprogramar@test.local")
    creado = await cliente_http.post("/turnos", headers=_auth(escena.token), json=escena.turno())
    turno_id = creado.json()["id"]

    movido = await cliente_http.post(
        f"/turnos/{turno_id}/reprogramacion",
        headers=_auth(escena.token),
        json={"inicio": (MARTES_15 + timedelta(hours=1)).isoformat()},
    )

    assert movido.status_code == 200, movido.text
    assert movido.json()["estado"] == "RESERVADO"
    assert movido.json()["inicio"].startswith("2027-09-07T19:00")


@pytest.mark.asyncio
async def test_la_disponibilidad_marca_lo_que_ya_esta_tomado(
    cliente_http: httpx.AsyncClient,
) -> None:
    escena = await _escena(cliente_http, "agenda-disponibilidad@test.local")
    creado = await cliente_http.post("/turnos", headers=_auth(escena.token), json=escena.turno())
    assert creado.status_code == 201, creado.text

    horarios = await cliente_http.get(
        "/turnos/disponibilidad",
        headers=_auth(escena.token),
        params={"recurso_id": escena.recurso_id, "fecha": "2027-09-07"},
    )

    assert horarios.status_code == 200, horarios.text
    cuerpo = horarios.json()
    # De 9 a 18 con turnos de una hora: nueve horarios.
    assert len(cuerpo["horarios"]) == 9
    tomados = [uno for uno in cuerpo["horarios"] if uno["ocupado"]]
    assert len(tomados) == 1
    assert tomados[0]["inicio"].startswith("2027-09-07T15:00")


@pytest.mark.asyncio
async def test_un_servicio_no_asociado_al_recurso_se_rechaza(
    cliente_http: httpx.AsyncClient,
) -> None:
    """HU-E7-04 RN-02 y HU-E7-06, tercer criterio."""
    escena = await _escena(cliente_http, "agenda-servicio@test.local")
    otro = await cliente_http.post(
        "/servicios",
        headers=_auth(escena.token),
        json={
            "nombre": "Color",
            "precio": "9000.00",
            "alicuota_iva": "0.21",
            "agendable": True,
            "duracion_estandar_min": 90,
        },
    )
    cuerpo = escena.turno()
    cuerpo["servicio_id"] = otro.json()["id"]

    rechazado = await cliente_http.post("/turnos", headers=_auth(escena.token), json=cuerpo)

    assert rechazado.status_code == 422, rechazado.text


@pytest.mark.asyncio
async def test_una_franja_invertida_no_crea_el_recurso(
    cliente_http: httpx.AsyncClient,
) -> None:
    """HU-E7-04, tercer criterio, con la frase de la historia cruzando el 422."""
    token = await _token(cliente_http, "agenda-horario@test.local")

    rechazado = await cliente_http.post(
        "/recursos",
        headers=_auth(token),
        json={
            "nombre": "Sala 2",
            "tipo": "ESPACIO",
            "patrones": [
                {
                    "dia_semana": 1,
                    "hora_inicio": "18:00:00",
                    "hora_fin": "09:00:00",
                    "duracion_slot_min": 60,
                }
            ],
        },
    )

    assert rechazado.status_code == 422, rechazado.text
    assert rechazado.json()["detalle"] == "La hora de inicio debe ser anterior a la hora de fin."


@pytest.mark.asyncio
async def test_la_segunda_excepcion_para_la_misma_fecha_se_rechaza(
    cliente_http: httpx.AsyncClient,
) -> None:
    """HU-E7-05, tercer criterio, con su frase."""
    escena = await _escena(cliente_http, "agenda-excepcion@test.local")
    ruta = f"/recursos/{escena.recurso_id}/excepciones"
    bloqueo = {"fecha": "2027-09-07", "tipo": "BLOQUEO"}

    primera = await cliente_http.post(ruta, headers=_auth(escena.token), json=bloqueo)
    assert primera.status_code == 201, primera.text

    segunda = await cliente_http.post(ruta, headers=_auth(escena.token), json=bloqueo)

    assert segunda.status_code == 422, segunda.text
    assert segunda.json()["detalle"] == "Ya existe una excepción para esa fecha en este recurso."


@pytest.mark.asyncio
async def test_un_dia_bloqueado_no_ofrece_horarios_ni_acepta_turnos(
    cliente_http: httpx.AsyncClient,
) -> None:
    """HU-E7-05, primer criterio: «el agente no ofrece ese día al reservar»."""
    escena = await _escena(cliente_http, "agenda-bloqueo@test.local")
    await cliente_http.post(
        f"/recursos/{escena.recurso_id}/excepciones",
        headers=_auth(escena.token),
        json={"fecha": "2027-09-07", "tipo": "BLOQUEO"},
    )

    horarios = await cliente_http.get(
        "/turnos/disponibilidad",
        headers=_auth(escena.token),
        params={"recurso_id": escena.recurso_id, "fecha": "2027-09-07"},
    )
    assert horarios.json()["horarios"] == []

    rechazado = await cliente_http.post("/turnos", headers=_auth(escena.token), json=escena.turno())
    assert rechazado.status_code == 422, rechazado.text


@pytest.mark.asyncio
async def test_desactivar_un_recurso_no_borra_sus_turnos(
    cliente_http: httpx.AsyncClient,
) -> None:
    """HU-E7-04, quinto criterio: los turnos se mantienen, las reservas nuevas no."""
    escena = await _escena(cliente_http, "agenda-desactivar@test.local")
    creado = await cliente_http.post("/turnos", headers=_auth(escena.token), json=escena.turno())
    turno_id = creado.json()["id"]

    apagado = await cliente_http.put(
        f"/recursos/{escena.recurso_id}/estado",
        headers=_auth(escena.token),
        json={"activo": False},
    )
    assert apagado.status_code == 200, apagado.text
    assert not apagado.json()["activo"]

    sigue = await cliente_http.get(f"/turnos/{turno_id}", headers=_auth(escena.token))
    assert sigue.json()["estado"] == "RESERVADO"

    nuevo = await cliente_http.post(
        "/turnos",
        headers=_auth(escena.token),
        json=escena.turno(MARTES_15 + timedelta(hours=2)),
    )
    assert nuevo.status_code == 422, nuevo.text


@pytest.mark.asyncio
async def test_una_empresa_no_ve_los_turnos_de_otra(cliente_http: httpx.AsyncClient) -> None:
    """RLS de punta a punta. La agenda es dónde está cada cliente a cada hora."""
    una = await _escena(cliente_http, "agenda-rls-a@test.local")
    otra = await _escena(cliente_http, "agenda-rls-b@test.local")
    creado = await cliente_http.post("/turnos", headers=_auth(una.token), json=una.turno())
    turno_id = creado.json()["id"]

    ajeno = await cliente_http.get(f"/turnos/{turno_id}", headers=_auth(otra.token))

    # «No es tuyo» y «no existe» son la misma respuesta a propósito.
    assert ajeno.status_code == 422, ajeno.text


@pytest.mark.asyncio
async def test_sin_sesion_no_se_llega_a_la_agenda(cliente_http: httpx.AsyncClient) -> None:
    for ruta in ("/turnos", "/recursos", "/recursos/servicios"):
        respuesta = await cliente_http.get(ruta)
        assert respuesta.status_code == 401, f"{ruta}: {respuesta.text}"


@pytest.mark.asyncio
async def test_los_servicios_agendables_excluyen_los_que_no_lo_son(
    cliente_http: httpx.AsyncClient,
) -> None:
    """HU-E7-04 RN-02: el selector de PAN-AGE-02 sólo ofrece lo que se puede reservar."""
    escena = await _escena(cliente_http, "agenda-catalogo@test.local")
    await cliente_http.post(
        "/servicios",
        headers=_auth(escena.token),
        json={
            "nombre": "Venta de producto",
            "precio": "3000.00",
            "alicuota_iva": "0.21",
            "agendable": False,
        },
    )

    agendables = await cliente_http.get("/recursos/servicios", headers=_auth(escena.token))

    assert agendables.status_code == 200, agendables.text
    nombres = [uno["nombre"] for uno in agendables.json()]
    assert nombres == ["Corte de pelo"]


@pytest.mark.asyncio
async def test_configurar_el_horario_lo_reemplaza_entero(
    cliente_http: httpx.AsyncClient,
) -> None:
    """HU-E7-04 RN-01. Reemplaza y no acumula: el martes deja de existir."""
    escena = await _escena(cliente_http, "agenda-horario-nuevo@test.local")

    actualizado = await cliente_http.put(
        f"/recursos/{escena.recurso_id}/disponibilidad",
        headers=_auth(escena.token),
        json={
            "patrones": [
                {
                    "dia_semana": 3,
                    "hora_inicio": "10:00:00",
                    "hora_fin": "14:00:00",
                    "duracion_slot_min": 30,
                }
            ]
        },
    )

    assert actualizado.status_code == 200, actualizado.text
    assert [uno["dia_semana"] for uno in actualizado.json()["patrones"]] == [3]

    horarios = await cliente_http.get(
        "/turnos/disponibilidad",
        headers=_auth(escena.token),
        params={"recurso_id": escena.recurso_id, "fecha": "2027-09-07"},
    )
    assert horarios.json()["horarios"] == []


@pytest.mark.asyncio
async def test_asociar_servicios_reemplaza_la_lista(cliente_http: httpx.AsyncClient) -> None:
    escena = await _escena(cliente_http, "agenda-asociar@test.local")

    vaciado = await cliente_http.put(
        f"/recursos/{escena.recurso_id}/servicios",
        headers=_auth(escena.token),
        json={"servicios": []},
    )

    assert vaciado.status_code == 200, vaciado.text
    assert vaciado.json()["servicios"] == []

    rechazado = await cliente_http.post("/turnos", headers=_auth(escena.token), json=escena.turno())
    assert rechazado.status_code == 422, rechazado.text


@pytest.mark.asyncio
async def test_quitar_la_excepcion_devuelve_el_dia_a_su_horario(
    cliente_http: httpx.AsyncClient,
) -> None:
    escena = await _escena(cliente_http, "agenda-quitar@test.local")
    await cliente_http.post(
        f"/recursos/{escena.recurso_id}/excepciones",
        headers=_auth(escena.token),
        json={"fecha": "2027-09-07", "tipo": "BLOQUEO"},
    )

    quitada = await cliente_http.delete(
        f"/recursos/{escena.recurso_id}/excepciones/2027-09-07", headers=_auth(escena.token)
    )

    assert quitada.status_code == 200, quitada.text
    assert quitada.json()["excepciones"] == []

    reservado = await cliente_http.post("/turnos", headers=_auth(escena.token), json=escena.turno())
    assert reservado.status_code == 201, reservado.text


@pytest.mark.asyncio
async def test_una_apertura_especial_reemplaza_el_horario_habitual(
    cliente_http: httpx.AsyncClient,
) -> None:
    """HU-E7-05, segundo criterio: ofrece el horario de la excepcion y no el habitual."""
    escena = await _escena(cliente_http, "agenda-apertura@test.local")

    puesta = await cliente_http.post(
        f"/recursos/{escena.recurso_id}/excepciones",
        headers=_auth(escena.token),
        json={
            "fecha": "2027-09-05",
            "tipo": "APERTURA_ESPECIAL",
            "franja_inicio": "2027-09-05T13:00:00+00:00",
            "franja_duracion_min": 120,
        },
    )
    assert puesta.status_code == 201, puesta.text

    horarios = await cliente_http.get(
        "/turnos/disponibilidad",
        headers=_auth(escena.token),
        params={"recurso_id": escena.recurso_id, "fecha": "2027-09-05"},
    )

    assert [uno["inicio"][11:16] for uno in horarios.json()["horarios"]] == ["10:00", "11:00"]


@pytest.mark.asyncio
async def test_solo_activos_filtra_el_listado_de_recursos(
    cliente_http: httpx.AsyncClient,
) -> None:
    escena = await _escena(cliente_http, "agenda-activos@test.local")
    await cliente_http.put(
        f"/recursos/{escena.recurso_id}/estado",
        headers=_auth(escena.token),
        json={"activo": False},
    )

    todos = await cliente_http.get("/recursos", headers=_auth(escena.token))
    activos = await cliente_http.get(
        "/recursos", headers=_auth(escena.token), params={"solo_activos": True}
    )

    assert len(todos.json()["recursos"]) == 1
    assert activos.json()["recursos"] == []
