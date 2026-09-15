"""Los dos adaptadores locales de almacenamiento, y la diferencia que importa.

`AlmacenamientoEnMemoria` alcanza para subir una planilla y mapearla. No alcanza para
procesarla: RN-01 hace el procesamiento asíncrono, así que quien lee los bytes es un worker
de Celery —otro proceso, otro `dict`— y el flujo moría en
`planilla_sin_archivo_para_procesar`.

Lo que se prueba acá es exactamente ese límite: que el de memoria **no** cruza procesos y
que el de disco sí. Un test que sólo guardara y leyera con la misma instancia pasaría con
los dos y no diría nada.
"""

from __future__ import annotations

import pytest
from cheatsheet.platform.almacenamiento import (
    AlmacenamientoEnDisco,
    AlmacenamientoEnMemoria,
)
from cheatsheet.platform.settings import Entorno

pytestmark = pytest.mark.asyncio

CLAVE = "empresa-abc/8b06cb4c-0fce-4c36-92a4-01b30bcf7dbe.xlsx"
CONTENIDO = b"PK\x03\x04 esto es un .xlsx de mentira"


async def test_lo_guardado_en_memoria_no_lo_ve_otra_instancia() -> None:
    """El defecto, escrito como prueba. Cada proceso construye el suyo."""
    del_api = AlmacenamientoEnMemoria(Entorno.LOCAL)
    await del_api.guardar(clave=CLAVE, contenido=CONTENIDO, tipo_de_contenido="application/xlsx")

    del_worker = AlmacenamientoEnMemoria(Entorno.LOCAL)
    with pytest.raises(FileNotFoundError):
        await del_worker.leer(CLAVE)


async def test_lo_guardado_en_disco_lo_lee_otra_instancia(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Y el arreglo: un directorio es un lugar, no un estado de proceso."""
    del_api = AlmacenamientoEnDisco(Entorno.LOCAL, str(tmp_path))
    await del_api.guardar(clave=CLAVE, contenido=CONTENIDO, tipo_de_contenido="application/xlsx")

    del_worker = AlmacenamientoEnDisco(Entorno.LOCAL, str(tmp_path))
    assert await del_worker.leer(CLAVE) == CONTENIDO


async def test_dos_claves_distintas_no_colisionan_al_aplanarse(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """La clave se aplana a un nombre de archivo, así que vale comprobar que sigue siendo única."""
    disco = AlmacenamientoEnDisco(Entorno.LOCAL, str(tmp_path))
    await disco.guardar(clave="a/uno.xlsx", contenido=b"uno", tipo_de_contenido="x")
    await disco.guardar(clave="b/uno.xlsx", contenido=b"dos", tipo_de_contenido="x")

    assert await disco.leer("a/uno.xlsx") == b"uno"
    assert await disco.leer("b/uno.xlsx") == b"dos"


async def test_un_archivo_eliminado_deja_de_leerse(tmp_path) -> None:  # type: ignore[no-untyped-def]
    disco = AlmacenamientoEnDisco(Entorno.LOCAL, str(tmp_path))
    await disco.guardar(clave=CLAVE, contenido=CONTENIDO, tipo_de_contenido="x")
    await disco.eliminar(CLAVE)

    with pytest.raises(FileNotFoundError):
        await disco.leer(CLAVE)
    # Desvincular dos veces es una operación legítima y no tiene por qué fallar.
    await disco.eliminar(CLAVE)


async def test_ninguno_de_los_dos_se_construye_en_produccion(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """La misma guarda que los adaptadores simulados de ARCA, WhatsApp y MercadoPago."""
    with pytest.raises(RuntimeError, match="produccion"):
        AlmacenamientoEnMemoria(Entorno.PRODUCTION)
    with pytest.raises(RuntimeError, match="produccion"):
        AlmacenamientoEnDisco(Entorno.PRODUCTION, str(tmp_path))
