"""La reportería de punta a punta (HU-E10-01 … HU-E10-06).

Las costuras que ninguna prueba unitaria mira:

1. **Que los cuatro ACL lean datos de verdad.** El tablero cruza `billing`, `payments`,
   `scheduling` y `observability`; los dobles del test unitario devuelven números fijos, así
   que la única forma de saber que las consultas son correctas es correrlas contra el motor.
   Acá la métrica que se comprueba es **operaciones**, que se llena sola: cada request del
   propio test deja una fila de bitácora.

2. **Que el mensaje de un período sin datos llegue a la pantalla.** El caso de uso levanta
   `SinDatosEnElPeriodo`, `api/errors.py` lo mapea a 422 y el `detalle` viaja: tres capas que
   sólo se prueban juntas desde afuera.

3. **Que la ruta del contador conteste sin sesión** — y que deje de contestar en cuanto el
   administrador revoca, con la frase exacta de HU-E10-06.

4. **Que la descarga salga con sus bytes y su nombre.** Un `Content-Disposition` mal armado se
   ve cuando alguien baja un archivo llamado `descarga`, no antes.
"""

from __future__ import annotations

import os
import zipfile
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from cheatsheet.api.dependencies import Recursos
from cheatsheet.api.main import create_app
from cheatsheet.contexts.payments.domain.cobro import Cobro, LinkDePago
from cheatsheet.contexts.payments.infrastructure.repositories import RepositorioCobroPostgres
from cheatsheet.contexts.reporting.domain.paquete import (
    MENSAJE_ACCESO_NO_DISPONIBLE,
    MENSAJE_SIN_EMAIL,
    TokenDeAccesoContable,
)
from cheatsheet.contexts.reporting.domain.reporte import MENSAJE_SIN_DATOS
from cheatsheet.contexts.reporting.infrastructure.acceso import EnlaceContableAleatorio
from cheatsheet.contexts.reporting.infrastructure.repositories import (
    RepositorioPaquetePostgres,
    RepositorioTokenContablePostgres,
)
from cheatsheet.platform.database import crear_sessionmaker, sesion_de_empresa
from cheatsheet.platform.settings import Settings
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import settings_de_prueba
from tests.integracion.conftest import requiere_base
from tests.integracion.test_api_bitacora import _sesion_de_solo_lectura

pytestmark = [requiere_base, pytest.mark.integration]

CONTRASENA = "una-contrasena-larga"
ENLACE = "un-enlace-de-prueba-de-32-caracteres"


def _settings() -> Settings:
    return replace(
        settings_de_prueba(),
        database_url=os.environ["DATABASE_URL"],
        database_url_migrations=os.environ["DATABASE_URL_MIGRATIONS"],
        redis_url=os.environ.get("REDIS_URL", "redis://127.0.0.1:6381/0"),
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


async def _sesion_admin(http: httpx.AsyncClient) -> tuple[str, EmpresaId]:
    respuesta = await http.post(
        "/auth/registro",
        json={
            "email": f"{uuid4()}@cheatsheet.ar",
            "contrasena": CONTRASENA,
            "nombre": "Ana Perez",
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    return str(cuerpo["access_token"]), EmpresaId(UUID(cuerpo["empresa_id"]))


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _sembrar_enlace(empresa_id: EmpresaId, paquete_id: str) -> None:
    """Deja un token con un valor conocido, que es lo único que el mail no puede darle al test.

    El enlace en claro existe **una sola vez**, en el correo. Un test que quisiera obtenerlo
    del sistema estaría probando algo que el sistema no hace; lo que se prueba acá es la ruta,
    así que el token se siembra con un digesto conocido, exactamente como lo guardaría el caso
    de uso.
    """
    engine = create_async_engine(os.environ["DATABASE_URL"])
    sesiones = crear_sessionmaker(engine)
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioTokenContablePostgres(sesion).agregar(
            TokenDeAccesoContable(
                id=uuid4(),
                paquete_id=UUID(paquete_id),
                empresa_id=empresa_id,
                valor_hash=EnlaceContableAleatorio().hashear(ENLACE),
                email_contador="contador@estudio.com.ar",
                vencimiento=datetime.now(tz=UTC) + timedelta(days=30),
                created_at=datetime.now(tz=UTC),
            )
        )
    await engine.dispose()


async def _revocar(empresa_id: EmpresaId) -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    sesiones = crear_sessionmaker(engine)
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repo = RepositorioTokenContablePostgres(sesion)
        token = await repo.activo_de_la_empresa()
        assert token is not None
        token.revocar()
        await repo.guardar(token)
    await engine.dispose()


# ------------------------------------------------------------------ el tablero


@pytest.mark.asyncio
async def test_el_tablero_cuenta_las_operaciones_reales(cliente_http: httpx.AsyncClient) -> None:
    """La métrica que se llena sola: cada request deja una fila de bitácora.

    Es lo que prueba que `BitacoraViaObservability` consulta bien — un `count` sobre la tabla
    real, acotado por RLS y por el período.
    """
    token, _ = await _sesion_admin(cliente_http)

    respuesta = await cliente_http.get("/reporteria/tablero", headers=_auth(token))
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()

    assert int(cuerpo["operaciones"]["valor"]) >= 1
    assert not cuerpo["sin_actividad"]
    # Los importes viajan como texto, nunca como número JSON.
    assert isinstance(cuerpo["facturado"]["valor"], str)


@pytest.mark.asyncio
async def test_el_tablero_de_un_mes_viejo_no_tiene_actividad(
    cliente_http: httpx.AsyncClient,
) -> None:
    token, _ = await _sesion_admin(cliente_http)
    respuesta = await cliente_http.get(
        "/reporteria/tablero",
        headers=_auth(token),
        params={"desde": "2020-01-01", "hasta": "2020-01-31"},
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["sin_actividad"]


@pytest.mark.asyncio
async def test_la_previsualizacion_no_deja_reportes(cliente_http: httpx.AsyncClient) -> None:
    """HU-E10-02 RN-03, comprobado desde afuera: tres previsualizaciones, cero filas."""
    token, _ = await _sesion_admin(cliente_http)
    for _ in range(3):
        respuesta = await cliente_http.get(
            "/reporteria/previsualizacion",
            headers=_auth(token),
            params={"tipo": "OPERACIONES"},
        )
        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json()["hay_datos"]

    historial = await cliente_http.get("/reporteria/reportes", headers=_auth(token))
    assert historial.json()["reportes"] == []


# ------------------------------------------------------------------ generar y descargar


@pytest.mark.asyncio
async def test_generar_y_descargar_un_reporte_de_operaciones(
    cliente_http: httpx.AsyncClient,
) -> None:
    token, _ = await _sesion_admin(cliente_http)

    creado = await cliente_http.post(
        "/reporteria/reportes",
        headers=_auth(token),
        json={"tipo": "OPERACIONES", "formato": "CSV"},
    )
    assert creado.status_code == 201, creado.text
    reporte = creado.json()
    assert reporte["descargable"]

    archivo = await cliente_http.get(
        f"/reporteria/reportes/{reporte['id']}/archivo", headers=_auth(token)
    )
    assert archivo.status_code == 200
    assert archivo.headers["content-type"].startswith("text/csv")
    assert "attachment" in archivo.headers["content-disposition"]
    # El BOM que hace que Excel en español abra los acentos bien.
    assert archivo.content.startswith(b"\xef\xbb\xbf")
    assert b"reporting" in archivo.content or b"identity" in archivo.content

    historial = await cliente_http.get("/reporteria/reportes", headers=_auth(token))
    assert len(historial.json()["reportes"]) == 1


@pytest.mark.asyncio
async def test_un_periodo_sin_datos_da_la_frase_de_la_historia(
    cliente_http: httpx.AsyncClient,
) -> None:
    token, _ = await _sesion_admin(cliente_http)
    respuesta = await cliente_http.post(
        "/reporteria/reportes",
        headers=_auth(token),
        params={"desde": "2020-01-01", "hasta": "2020-01-31"},
        json={"tipo": "FACTURACION", "formato": "CSV"},
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["detalle"] == MENSAJE_SIN_DATOS


@pytest.mark.asyncio
async def test_un_formato_que_el_tipo_no_admite_se_rechaza(
    cliente_http: httpx.AsyncClient,
) -> None:
    token, _ = await _sesion_admin(cliente_http)
    respuesta = await cliente_http.post(
        "/reporteria/reportes",
        headers=_auth(token),
        json={"tipo": "OPERACIONES", "formato": "PDF"},
    )
    assert respuesta.status_code == 422


# ------------------------------------------------------------------ el paquete contable


@pytest.mark.asyncio
async def test_configurar_el_envio_automatico(cliente_http: httpx.AsyncClient) -> None:
    token, _ = await _sesion_admin(cliente_http)

    inicial = await cliente_http.get("/reporteria/configuracion", headers=_auth(token))
    assert inicial.status_code == 200, inicial.text
    assert not inicial.json()["activo"]
    assert inicial.json()["proximo_envio"] is None

    guardada = await cliente_http.put(
        "/reporteria/configuracion",
        headers=_auth(token),
        json={
            "dia_de_envio": 10,
            "formatos": ["PDF", "XML"],
            "contenido": ["FACTURAS", "REPORTE_DE_COBROS"],
            "email_contador": "contador@estudio.com.ar",
            "activo": True,
        },
    )
    assert guardada.status_code == 200, guardada.text
    cuerpo = guardada.json()
    assert cuerpo["activo"]
    assert cuerpo["dia_de_envio"] == 10
    assert cuerpo["proximo_envio"] is not None
    assert cuerpo["contenido"] == ["FACTURAS", "REPORTE_DE_COBROS"]


@pytest.mark.asyncio
async def test_activar_sin_email_da_el_texto_de_la_historia(
    cliente_http: httpx.AsyncClient,
) -> None:
    token, _ = await _sesion_admin(cliente_http)
    respuesta = await cliente_http.put(
        "/reporteria/configuracion",
        headers=_auth(token),
        json={
            "dia_de_envio": 5,
            "formatos": ["PDF"],
            "contenido": ["FACTURAS"],
            "email_contador": None,
            "activo": True,
        },
    )
    assert respuesta.status_code == 409
    assert respuesta.json()["detalle"] == MENSAJE_SIN_EMAIL


@pytest.mark.asyncio
async def test_el_paquete_de_prueba_sale_como_zip(cliente_http: httpx.AsyncClient) -> None:
    """Cuarto criterio de HU-E10-04: «lo deja disponible para descarga inmediata»."""
    token, _ = await _sesion_admin(cliente_http)

    creado = await cliente_http.post("/reporteria/paquetes", headers=_auth(token), json={})
    assert creado.status_code == 201, creado.text
    paquete = creado.json()
    assert paquete["disponible"]

    archivo = await cliente_http.get(
        f"/reporteria/paquetes/{paquete['id']}/archivo", headers=_auth(token)
    )
    assert archivo.status_code == 200
    assert archivo.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(BytesIO(archivo.content)) as zip_:
        assert zip_.namelist() == [] or "operaciones.csv" in zip_.namelist()


@pytest.mark.asyncio
async def test_invitar_al_contador_y_no_poder_invitar_a_otro(
    cliente_http: httpx.AsyncClient,
) -> None:
    token, _ = await _sesion_admin(cliente_http)
    await cliente_http.post("/reporteria/paquetes", headers=_auth(token), json={})

    invitado = await cliente_http.post(
        "/reporteria/contador",
        headers=_auth(token),
        json={"email": "contador@estudio.com.ar"},
    )
    assert invitado.status_code == 201, invitado.text
    cuerpo = invitado.json()
    assert cuerpo["invitado"]
    # La respuesta **no lleva el enlace**: el enlace va al mail del contador.
    assert "enlace" not in cuerpo

    segundo = await cliente_http.post(
        "/reporteria/contador", headers=_auth(token), json={"email": "otro@estudio.com.ar"}
    )
    assert segundo.status_code == 409

    revocado = await cliente_http.delete("/reporteria/contador", headers=_auth(token))
    assert revocado.status_code == 204

    tercero = await cliente_http.post(
        "/reporteria/contador", headers=_auth(token), json={"email": "otro@estudio.com.ar"}
    )
    assert tercero.status_code == 201, tercero.text


@pytest.mark.asyncio
async def test_un_email_invalido_no_invita(cliente_http: httpx.AsyncClient) -> None:
    token, _ = await _sesion_admin(cliente_http)
    await cliente_http.post("/reporteria/paquetes", headers=_auth(token), json={})
    respuesta = await cliente_http.post(
        "/reporteria/contador", headers=_auth(token), json={"email": "no-es-un-email"}
    )
    assert respuesta.status_code == 422


async def _sembrar_cobros_de_marzo(empresa_id: EmpresaId) -> None:
    """Un cobro creado el 10/2 y pagado el 5/3, y otro pendiente creado el 6/3."""
    creado = datetime(2026, 2, 10, 12, 0, tzinfo=UTC)
    pagado_el = datetime(2026, 3, 5, 12, 0, tzinfo=UTC)
    cliente_id = uuid4()
    engine = create_async_engine(os.environ["DATABASE_URL"])
    sesiones = crear_sessionmaker(engine)
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await sesion.execute(
            text(
                "INSERT INTO cliente (id, empresa_id, nombre, origen, activo, created_at, "
                "updated_at) VALUES (:id, :empresa_id, 'Acme SA', 'PANEL', true, :ahora, :ahora)"
            ),
            {"id": cliente_id, "empresa_id": empresa_id, "ahora": creado},
        )
        repo = RepositorioCobroPostgres(sesion)
        for monto, fecha, preferencia in (
            ("1000.00", creado, "pref-api-1"),
            ("500.00", datetime(2026, 3, 6, 12, 0, tzinfo=UTC), "pref-api-2"),
        ):
            cobro = Cobro(
                id=uuid4(),
                empresa_id=empresa_id,
                cliente_id=cliente_id,
                monto=Decimal(monto),
                descripcion="Consulta",
                vence_el=fecha + timedelta(days=30),
                created_at=fecha,
                updated_at=fecha,
            )
            cobro.asignar_link(
                LinkDePago(preference_id=preferencia, url=f"https://mp.com/{preferencia}"), fecha
            )
            if monto == "1000.00":
                cobro.aprobar(payment_id=f"pago-{cobro.id}", ahora=pagado_el, fecha_pago=pagado_el)
            await repo.agregar(cobro)
    await engine.dispose()


def _verificar_la_cobranza_de_marzo(cuerpo: dict[str, object]) -> None:
    # Pagado en marzo y creado en febrero: suma en «cobrado» y en la semana del 5/3 (W10).
    cobrado = cuerpo["cobrado"]
    assert isinstance(cobrado, dict)
    assert cobrado["valor"] == "1000.00"
    assert cuerpo["cobrado_por_semana"] == {"2026-W10": "1000.00"}
    # Marzo solo creo el cobro pendiente: el de febrero no entra en «cobros por estado».
    assert cuerpo["cobros_por_estado"] == {"PENDIENTE": {"cantidad": 1, "monto": "500.00"}}
    assert cuerpo["pendiente"] == "500.00"
    # Nada pagado de lo creado en marzo: la tasa es de la cohorte de marzo.
    assert cuerpo["tasa_de_cobro"] == "0.00"
    # Sin comprobantes ni turnos, pero con cobros: no es un periodo sin actividad.
    assert cuerpo["sin_actividad"] is False


@pytest.mark.asyncio
async def test_el_tablero_trae_la_cobranza_y_un_periodo_solo_con_cobros_tiene_actividad(
    cliente_http: httpx.AsyncClient,
) -> None:
    """HU-E10-01 RN-06 a RN-08: tasa de cobro, cobrado por semana y cobros por estado."""
    token, empresa_id = await _sesion_admin(cliente_http)
    await _sembrar_cobros_de_marzo(empresa_id)

    respuesta = await cliente_http.get(
        "/reporteria/tablero",
        headers=_auth(token),
        params={"desde": "2026-03-01", "hasta": "2026-03-31"},
    )

    assert respuesta.status_code == 200, respuesta.text
    _verificar_la_cobranza_de_marzo(respuesta.json())


@pytest.mark.asyncio
async def test_solo_lectura_ve_la_cobranza_del_tablero(cliente_http: httpx.AsyncClient) -> None:
    """RN-04 de HU-E10-01: son totales, y todos los roles los leen."""
    _, empresa_id = await _sesion_admin(cliente_http)
    await _sembrar_cobros_de_marzo(empresa_id)
    solo_lectura = await _sesion_de_solo_lectura(cliente_http, str(empresa_id))

    respuesta = await cliente_http.get(
        "/reporteria/tablero",
        headers=_auth(solo_lectura),
        params={"desde": "2026-03-01", "hasta": "2026-03-31"},
    )

    assert respuesta.status_code == 200, respuesta.text
    _verificar_la_cobranza_de_marzo(respuesta.json())


# ------------------------------------------------------------------ el contador externo


@pytest.mark.asyncio
async def test_el_contador_entra_sin_sesion_y_descarga(cliente_http: httpx.AsyncClient) -> None:
    """La única ruta del sistema que contesta sin `Authorization`.

    Prueba las tres capas juntas: la función `SECURITY DEFINER` que resuelve la empresa, la
    unidad de trabajo que se abre con ella, y la validación del token ya adentro de RLS.
    """
    token, empresa_id = await _sesion_admin(cliente_http)
    creado = await cliente_http.post("/reporteria/paquetes", headers=_auth(token), json={})
    paquete_id = creado.json()["id"]
    await _sembrar_enlace(empresa_id, paquete_id)

    acceso = await cliente_http.get(f"/contador/{ENLACE}")
    assert acceso.status_code == 200, acceso.text
    cuerpo = acceso.json()
    assert [uno["id"] for uno in cuerpo["paquetes"]["paquetes"]] == [paquete_id]
    # Ve el tablero, y nada más: ni clientes, ni comprobantes, ni cobros.
    assert set(cuerpo) == {"vence", "tablero", "paquetes"}
    # El tablero del contador lleva la misma forma, con la cobranza incluida (solo totales).
    assert {"tasa_de_cobro", "cobrado_por_semana", "cobros_por_estado"} <= set(cuerpo["tablero"])

    archivo = await cliente_http.get(f"/contador/{ENLACE}/paquetes/{paquete_id}")
    assert archivo.status_code == 200
    assert archivo.headers["content-type"] == "application/zip"


@pytest.mark.asyncio
async def test_los_accesos_del_contador_se_cuentan(cliente_http: httpx.AsyncClient) -> None:
    """HU-E10-06 RN-03: es lo único que hace auditable un acceso sin cuenta."""
    token, empresa_id = await _sesion_admin(cliente_http)
    creado = await cliente_http.post("/reporteria/paquetes", headers=_auth(token), json={})
    await _sembrar_enlace(empresa_id, creado.json()["id"])

    await cliente_http.get(f"/contador/{ENLACE}")
    await cliente_http.get(f"/contador/{ENLACE}")

    vista = await cliente_http.get("/reporteria/configuracion", headers=_auth(token))
    assert vista.json()["contador"]["accesos"] == 2


@pytest.mark.asyncio
async def test_revocar_corta_el_enlace_de_inmediato(cliente_http: httpx.AsyncClient) -> None:
    """HU-E10-06 RN-04, con la frase exacta que el criterio pide mostrar."""
    token, empresa_id = await _sesion_admin(cliente_http)
    creado = await cliente_http.post("/reporteria/paquetes", headers=_auth(token), json={})
    paquete_id = creado.json()["id"]
    await _sembrar_enlace(empresa_id, paquete_id)
    assert (await cliente_http.get(f"/contador/{ENLACE}")).status_code == 200

    await _revocar(empresa_id)

    negado = await cliente_http.get(f"/contador/{ENLACE}")
    assert negado.status_code == 422
    assert negado.json()["detalle"] == MENSAJE_ACCESO_NO_DISPONIBLE

    # Y también la descarga, no sólo la entrada: una pestaña abierta no sigue bajando nada.
    descarga = await cliente_http.get(f"/contador/{ENLACE}/paquetes/{paquete_id}")
    assert descarga.status_code == 422


@pytest.mark.asyncio
async def test_un_enlace_inventado_no_entra(cliente_http: httpx.AsyncClient) -> None:
    respuesta = await cliente_http.get("/contador/no-existe-este-enlace")
    assert respuesta.status_code == 422
    assert respuesta.json()["detalle"] == MENSAJE_ACCESO_NO_DISPONIBLE


@pytest.mark.asyncio
async def test_el_panel_sigue_exigiendo_sesion(cliente_http: httpx.AsyncClient) -> None:
    """Que `/contador/` sea público no aflojó nada más."""
    assert (await cliente_http.get("/reporteria/tablero")).status_code == 401
    assert (await cliente_http.get("/reporteria/paquetes")).status_code == 401


@pytest.mark.asyncio
async def test_un_paquete_de_otra_empresa_no_se_descarga_con_el_enlace(
    cliente_http: httpx.AsyncClient,
) -> None:
    """El enlace acota a **su** empresa: el id de un paquete ajeno no devuelve nada.

    No lo garantiza el router: lo garantiza que la sesión se abre con la empresa que resolvió
    el token, y que RLS acota todo lo que se lea adentro.
    """
    token_uno, empresa_uno = await _sesion_admin(cliente_http)
    creado_uno = await cliente_http.post("/reporteria/paquetes", headers=_auth(token_uno), json={})
    await _sembrar_enlace(empresa_uno, creado_uno.json()["id"])

    token_dos, _ = await _sesion_admin(cliente_http)
    creado_dos = await cliente_http.post("/reporteria/paquetes", headers=_auth(token_dos), json={})
    ajeno = creado_dos.json()["id"]

    respuesta = await cliente_http.get(f"/contador/{ENLACE}/paquetes/{ajeno}")
    assert respuesta.status_code == 422


@pytest.mark.asyncio
async def test_el_paquete_registra_totales(cliente_http: httpx.AsyncClient) -> None:
    token, empresa_id = await _sesion_admin(cliente_http)
    creado = await cliente_http.post("/reporteria/paquetes", headers=_auth(token), json={})
    assert creado.status_code == 201, creado.text

    engine = create_async_engine(os.environ["DATABASE_URL"])
    sesiones = crear_sessionmaker(engine)
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        paquetes = await RepositorioPaquetePostgres(sesion).listar()
    await engine.dispose()

    assert len(paquetes) == 1
    # Los cinco contenidos dejan su total, aunque no hayan producido archivo.
    assert set(paquetes[0].totales_por_tipo) == {
        "FACTURAS",
        "NOTAS_DE_CREDITO",
        "REPORTE_DE_COBROS",
        "LOG_DE_OPERACIONES",
        "RESUMEN_EJECUTIVO",
    }
