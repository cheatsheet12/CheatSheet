"""La migración 0036: plantillas en Meta (U6, casos 28 y 29).

Sube y baja sobre una base con plantillas existentes. Son síncronos a propósito, como
`test_migracion_0034.py`: `alembic.command` arranca su propio loop de asyncio. Necesitan
PostgreSQL: se saltean sin base y corren en CI.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from tests.integracion.conftest import RAIZ_BACKEND, requiere_base

pytestmark = [requiere_base, pytest.mark.integration]

AHORA = datetime(2026, 10, 6, 15, 0, tzinfo=UTC)

TEXTO_VIEJO_RECORDATORIO = (
    "Hola {{nombre}}, te recordamos el pago de {{concepto}} por $ {{monto}}. "
    "Podés pagarlo acá: {{link}}"
)
TEXTO_VIEJO_COBRO = (
    "Hola {{nombre}}, te dejamos el link para pagar {{concepto}} por $ {{monto}}: {{link}}"
)
TEXTO_EDITADO = "Hola {{nombre}}, este texto lo editó un administrador: {{link}}"

CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")
CREAR_PLANTILLA = text(
    "INSERT INTO plantilla_de_notificacion "
    "(id, empresa_id, codigo, idioma, canal, cuerpo, estado_aprobacion_meta, created_at) "
    "VALUES (:id, :empresa_id, :codigo, 'es_AR', :canal, :cuerpo, :estado, :ahora)"
)
CREAR_INTEGRACION = text(
    "INSERT INTO configuracion_de_integracion "
    "(id, empresa_id, sistema, credencial_contenido_cifrado, credencial_algoritmo, parametros, "
    "ambiente, estado) "
    "VALUES (:id, :empresa_id, 'WHATSAPP', '\\x00', 'x', CAST(:parametros AS jsonb), "
    "'SANDBOX', :estado)"
)
LEER_PLANTILLA = text(
    "SELECT estado_aprobacion_meta, cuerpo, nombre_en_meta FROM plantilla_de_notificacion "
    "WHERE empresa_id = :empresa_id AND codigo = :codigo"
)
COLUMNAS = text(
    "SELECT count(*) FROM information_schema.columns WHERE table_name = "
    "'plantilla_de_notificacion' AND column_name IN ('nombre_en_meta', 'meta_plantilla_id', "
    "'motivo_meta', 'detalle_meta', 'categoria_en_meta', 'enviada_a_meta_en', 'estado_meta_en')"
)
FUNCIONES = text(
    "SELECT count(*) FROM pg_proc WHERE proname IN "
    "('empresas_con_whatsapp_conectado', 'empresa_de_la_cuenta_de_whatsapp')"
)
INDICE_WABA_UNICO = text("SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_integracion_waba'")


def _config() -> Config:
    config = Config(str(RAIZ_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(RAIZ_BACKEND / "migrations"))
    return config


def _motor(variable: str = "DATABASE_URL_MIGRATIONS") -> AsyncEngine:
    """El rol dueño ve todas las empresas (`BYPASSRLS`, ADR-0005); `DATABASE_URL` es el de la app."""
    return create_async_engine(os.environ[variable])


async def _ejecutar(sentencia: object, parametros: list[dict[str, object]]) -> None:
    motor = _motor()
    try:
        async with motor.begin() as conexion:
            for fila in parametros:
                await conexion.execute(sentencia, fila)  # type: ignore[call-overload]
    finally:
        await motor.dispose()


async def _leer(
    sentencia: object,
    parametros: dict[str, object] | None = None,
    *,
    variable: str = "DATABASE_URL_MIGRATIONS",
) -> list[tuple[object, ...]]:
    motor = _motor(variable)
    try:
        async with motor.connect() as conexion:
            filas = (await conexion.execute(sentencia, parametros or {})).all()  # type: ignore[call-overload]
    finally:
        await motor.dispose()
    return [tuple(fila) for fila in filas]


def _plantilla(
    empresa_id: uuid.UUID, codigo: str, canal: str, cuerpo: str, estado: str
) -> dict[str, object]:
    return {
        "id": uuid.uuid4(),
        "empresa_id": empresa_id,
        "codigo": codigo,
        "canal": canal,
        "cuerpo": cuerpo,
        "estado": estado,
        "ahora": AHORA,
    }


@pytest.fixture
def esquema_en_0035(esquema_migrado: None) -> Iterator[None]:
    """Baja a `0035`, la de `develop` (solo se deshace la de plantillas) y, pase lo que pase, deja el esquema en `head` para el resto."""
    config = _config()
    command.downgrade(config, "0035")
    try:
        yield
    finally:
        command.upgrade(config, "head")


def _sembrar_plantillas_viejas() -> uuid.UUID:
    empresa_id = uuid.uuid4()
    asyncio.run(_ejecutar(CREAR_EMPRESA, [{"id": empresa_id}]))
    asyncio.run(
        _ejecutar(
            CREAR_PLANTILLA,
            [
                _plantilla(
                    empresa_id,
                    "recordatorio_de_cobro",
                    "WHATSAPP",
                    TEXTO_VIEJO_RECORDATORIO,
                    "PENDIENTE",
                ),
                _plantilla(empresa_id, "cobro_generado", "WHATSAPP", TEXTO_EDITADO, "PENDIENTE"),
                _plantilla(
                    empresa_id, "turno_cancelado", "WHATSAPP", "Hola {{nombre}}.", "RECHAZADA"
                ),
            ],
        )
    )
    return empresa_id


def test_downgrade_deja_la_tabla_sin_las_columnas_ni_las_funciones(esquema_en_0035: None) -> None:
    assert asyncio.run(_leer(COLUMNAS)) == [(0,)]
    assert asyncio.run(_leer(FUNCIONES)) == [(0,)]


def test_el_backfill_pasa_pendiente_a_sin_enviar_y_pone_el_nombre(esquema_en_0035: None) -> None:
    """Caso 28: nadie las mandó nunca, así que «pendiente» era falso."""
    empresa_id = _sembrar_plantillas_viejas()

    command.upgrade(_config(), "head")

    recordatorio = asyncio.run(
        _leer(LEER_PLANTILLA, {"empresa_id": empresa_id, "codigo": "recordatorio_de_cobro"})
    )
    rechazada = asyncio.run(
        _leer(LEER_PLANTILLA, {"empresa_id": empresa_id, "codigo": "turno_cancelado"})
    )
    assert recordatorio[0][0] == "SIN_ENVIAR"
    assert recordatorio[0][2] == "recordatorio_de_cobro"
    assert rechazada[0][0] == "RECHAZADA"  # solo el PENDIENTE cambia


def test_el_texto_de_fabrica_viejo_pasa_al_nuevo_y_el_editado_queda_igual(
    esquema_en_0035: None,
) -> None:
    empresa_id = _sembrar_plantillas_viejas()

    command.upgrade(_config(), "head")

    recordatorio = asyncio.run(
        _leer(LEER_PLANTILLA, {"empresa_id": empresa_id, "codigo": "recordatorio_de_cobro"})
    )
    editado = asyncio.run(
        _leer(LEER_PLANTILLA, {"empresa_id": empresa_id, "codigo": "cobro_generado"})
    )
    assert recordatorio[0][1] == TEXTO_VIEJO_RECORDATORIO + " Gracias."
    assert editado[0][1] == TEXTO_EDITADO


def test_las_funciones_devuelven_solo_el_id_de_la_empresa_y_la_app_puede_ejecutarlas(
    esquema_migrado: None,
) -> None:
    """Caso 29: `cheatsheet_app` no ve la tabla sin empresa, pero sí estas dos funciones."""
    empresa_id, otra = uuid.uuid4(), uuid.uuid4()
    waba = f"waba-{uuid.uuid4()}"
    asyncio.run(_ejecutar(CREAR_EMPRESA, [{"id": empresa_id}, {"id": otra}]))
    asyncio.run(
        _ejecutar(
            CREAR_INTEGRACION,
            [
                {
                    "id": uuid.uuid4(),
                    "empresa_id": empresa_id,
                    "parametros": f'{{"waba_id": "{waba}"}}',
                    "estado": "CONECTADO",
                },
                {
                    "id": uuid.uuid4(),
                    "empresa_id": otra,
                    "parametros": "{}",
                    "estado": "CONECTADO",
                },
            ],
        )
    )

    por_waba = asyncio.run(
        _leer(
            text("SELECT * FROM empresa_de_la_cuenta_de_whatsapp(:waba)"),
            {"waba": waba},
            variable="DATABASE_URL",
        )
    )
    conectadas = asyncio.run(
        _leer(
            text("SELECT * FROM empresas_con_whatsapp_conectado()"),
            variable="DATABASE_URL",
        )
    )

    assert por_waba == [(empresa_id,)]
    assert (empresa_id,) in conectadas
    assert (otra,) not in conectadas  # sin `waba_id` no hay a quién preguntarle


def test_el_indice_de_la_cuenta_es_unico_y_el_downgrade_lo_saca(esquema_migrado: None) -> None:
    """G4: dos empresas no comparten una WABA. Es parcial: solo WhatsApp y solo con id cargado."""
    definicion = asyncio.run(_leer(INDICE_WABA_UNICO))
    assert len(definicion) == 1
    assert "UNIQUE" in str(definicion[0][0])

    command.downgrade(_config(), "0035")
    try:
        assert asyncio.run(_leer(INDICE_WABA_UNICO)) == []
    finally:
        command.upgrade(_config(), "head")
