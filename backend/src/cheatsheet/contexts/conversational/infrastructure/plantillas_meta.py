"""El cliente de las plantillas de WhatsApp de una empresa: crear, editar y leer su estado (U6).

Habla con la Business Management API de Meta, **sobre la WABA de la empresa** (no sobre el número
que manda mensajes). Las tres operaciones:

- `crear`: `POST /{waba_id}/message_templates`. Categoría **UTILITY** (confirmaciones, avisos y
  recordatorios de una transacción existente), parámetros **con nombre** y un ejemplo por variable,
  que Meta exige para revisar el texto.
- `editar`: `POST /{template_id}`. Reemplaza todos los componentes; nombre e idioma son inmutables.
- `estados`: `GET /{waba_id}/message_templates`, paginado, con un tope de páginas.

Comparte con el envío de mensajes el bucle de reintento y la clasificación (`canal_http.py`):
transitorio se reintenta con espera, permanente y **timeout de lectura no** (un duplicado al crear
o editar es peor que un faltante: la conciliación detecta el texto divergente). Un rechazo lleva el
`error_user_msg` de Meta —habla de nuestro texto, no de datos personales— y **nunca va a un log**.

`PlantillasSimuladas` aprueba todo y se niega a arrancar en producción; `SinCuentaDeMeta` es lo que
recibe una empresa sin WhatsApp conectado en producción: levanta `CanalNoConectado`.

**No importa a `business_config`** (R3): sus tipos de respuesta son propios y la raíz de
composición los traduce.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx

from cheatsheet.contexts.conversational.application.errors import CanalNoConectado, EnvioIncierto
from cheatsheet.contexts.conversational.infrastructure.canal_http import Esperar, pedir_a_meta
from cheatsheet.platform.settings import Entorno
from cheatsheet.platform.telemetry import obtener_logger

logger = obtener_logger(__name__)

#: Las seis plantillas son confirmaciones, avisos y recordatorios de algo que el cliente ya hizo.
CATEGORIA = "UTILITY"

#: Tope de páginas de `estados()`: una empresa tiene a lo sumo seis plantillas propias, así que
#: pasar de ahí es un cursor que no termina y no una WABA con mucho para leer.
MAXIMO_DE_PAGINAS = 10

#: Lo que se pide en cada nodo. `rejected_reason` y `components` hacen falta para el motivo y para
#: detectar un texto divergente (D-U6-5).
CAMPOS = "id,name,language,status,category,rejected_reason,components"

#: Meta devuelve «NONE» cuando no hay motivo de rechazo.
SIN_MOTIVO = "NONE"

SIN_CUENTA = "La empresa no conectó WhatsApp: no hay una cuenta de Meta para las plantillas"


@dataclass(frozen=True, slots=True)
class RespuestaDePlantilla:
    """Lo que Meta contesta al crear o editar."""

    meta_plantilla_id: str
    estado: str
    categoria: str | None


@dataclass(frozen=True, slots=True)
class PlantillaEnMeta:
    """Una plantilla tal como está en la WABA."""

    meta_plantilla_id: str
    nombre: str
    idioma: str
    estado: str
    categoria: str | None
    motivo: str | None
    cuerpo: str | None


def _componentes(cuerpo: str, ejemplos: Mapping[str, str]) -> list[dict[str, Any]]:
    componente: dict[str, Any] = {"type": "BODY", "text": cuerpo}
    if ejemplos:
        componente["example"] = {
            "body_text_named_params": [
                {"param_name": nombre, "example": valor} for nombre, valor in ejemplos.items()
            ]
        }
    return [componente]


class PlantillasDeMeta:
    """El cliente real. Timeout explícito, reintento con espera y fallo tipado."""

    def __init__(
        self,
        *,
        token: str,
        waba_id: str,
        graph_url: str,
        graph_version: str,
        timeout_segundos: float,
        transporte: httpx.AsyncBaseTransport | None = None,
        esperar: Esperar = asyncio.sleep,
    ) -> None:
        self._token = token
        self._waba_id = waba_id
        self._base = f"{graph_url.rstrip('/')}/{graph_version}"
        self._timeout = timeout_segundos
        self._transporte = transporte
        self._esperar = esperar

    async def crear(
        self, *, nombre: str, idioma: str, cuerpo: str, ejemplos: Mapping[str, str]
    ) -> RespuestaDePlantilla:
        datos = await self._pedir(
            "POST",
            f"{self._base}/{self._waba_id}/message_templates",
            cuerpo={
                "name": nombre,
                "language": idioma,
                "category": CATEGORIA,
                "parameter_format": "named",
                "components": _componentes(cuerpo, ejemplos),
            },
        )
        identificador = datos.get("id")
        if not isinstance(identificador, str) or not identificador:
            # El pedido salió y Meta contestó 2xx: la plantilla probablemente existe. No se
            # inventa un id; la conciliación la encuentra por nombre antes de crearla otra vez.
            logger.warning("plantilla_creada_sin_id")
            raise EnvioIncierto("Meta aceptó la plantilla pero no devolvió su id")
        estado = datos.get("status")
        categoria = datos.get("category")
        return RespuestaDePlantilla(
            meta_plantilla_id=identificador,
            estado=estado if isinstance(estado, str) else "PENDING",
            categoria=categoria if isinstance(categoria, str) else None,
        )

    async def editar(
        self, *, meta_plantilla_id: str, cuerpo: str, ejemplos: Mapping[str, str]
    ) -> RespuestaDePlantilla:
        await self._pedir(
            "POST",
            f"{self._base}/{meta_plantilla_id}",
            cuerpo={"components": _componentes(cuerpo, ejemplos)},
        )
        # Meta no dice en qué estado queda una plantilla recién editada (TODO §22.43): hasta
        # que el webhook o la conciliación lo confirmen, se la trata como pendiente.
        return RespuestaDePlantilla(
            meta_plantilla_id=meta_plantilla_id, estado="PENDING", categoria=None
        )

    @property
    def estados_completos(self) -> bool:
        return True

    async def estados(self) -> list[PlantillaEnMeta]:
        """La lista entera de la WABA, o `EnvioIncierto`: nunca una parte como si fuera el todo.

        Quien la usa deduce lo que **falta** (una aprobada que Meta ya no lista), así que una
        lectura cortada —páginas de más, una respuesta que no es una lista, una fila con id pero
        ilegible— tiene que ser un error y no una lista más corta.
        """
        plantillas: list[PlantillaEnMeta] = []
        cursor: str | None = None
        for _ in range(MAXIMO_DE_PAGINAS):
            parametros = {"fields": CAMPOS, "limit": "100"}
            if cursor is not None:
                parametros["after"] = cursor
            datos = await self._pedir(
                "GET", f"{self._base}/{self._waba_id}/message_templates", parametros=parametros
            )
            plantillas.extend(_leer_filas(datos.get("data")))
            cursor = _siguiente_cursor(datos.get("paging"))
            if cursor is None:
                return plantillas
        raise EnvioIncierto("La lista de plantillas de Meta tiene más páginas de las que se leen")

    async def _pedir(
        self,
        metodo: str,
        ruta: str,
        *,
        cuerpo: Mapping[str, object] | None = None,
        parametros: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transporte) as cliente:
            respuesta = await pedir_a_meta(
                cliente,
                metodo,
                ruta,
                token=self._token,
                objeto="la plantilla",
                cuerpo=cuerpo,
                parametros=parametros,
                esperar=self._esperar,
                con_mensaje=True,
            )
        try:
            datos = respuesta.json()
        except ValueError:
            return {}
        return datos if isinstance(datos, dict) else {}


def _siguiente_cursor(paginacion: object) -> str | None:
    if not isinstance(paginacion, dict) or not paginacion.get("next"):
        return None
    cursores = paginacion.get("cursors")
    despues = cursores.get("after") if isinstance(cursores, dict) else None
    return despues if isinstance(despues, str) and despues else None


def _leer_filas(filas: object) -> list[PlantillaEnMeta]:
    """Las plantillas bien formadas.

    Una fila sin forma de plantilla (sin id, o que no es un objeto) se ignora. **Una fila con id
    pero ilegible no**: podría ser una plantilla nuestra, y ignorarla la haría pasar por borrada.
    Una respuesta que no es una lista tampoco es una lista vacía.
    """
    if not isinstance(filas, list):
        raise EnvioIncierto("Meta contestó la lista de plantillas con una forma inesperada")
    leidas: list[PlantillaEnMeta] = []
    for fila in filas:
        if not isinstance(fila, dict):
            continue
        identificador, nombre, estado = fila.get("id"), fila.get("name"), fila.get("status")
        if not (
            isinstance(identificador, str) and isinstance(nombre, str) and isinstance(estado, str)
        ):
            if isinstance(identificador, str):
                raise EnvioIncierto("Meta contestó una plantilla con una forma inesperada")
            continue
        idioma, categoria, motivo = (
            fila.get("language"),
            fila.get("category"),
            fila.get("rejected_reason"),
        )
        leidas.append(
            PlantillaEnMeta(
                meta_plantilla_id=identificador,
                nombre=nombre,
                idioma=idioma if isinstance(idioma, str) else "",
                estado=estado,
                categoria=categoria if isinstance(categoria, str) else None,
                motivo=motivo if isinstance(motivo, str) and motivo != SIN_MOTIVO else None,
                cuerpo=_cuerpo_de(fila.get("components")),
            )
        )
    return leidas


def _cuerpo_de(componentes: object) -> str | None:
    if not isinstance(componentes, list):
        return None
    for componente in componentes:
        if isinstance(componente, dict) and componente.get("type") == "BODY":
            texto = componente.get("text")
            return texto if isinstance(texto, str) else None
    return None


class PlantillasSimuladas:
    """El doble: aprueba todo, sin red. **Rechazado en producción.**

    Una empresa cuyas plantillas «se aprueban» sin que Meta las haya visto es una empresa cuyos
    mensajes salen como plantilla que no existe y fallan fuera de la ventana. `estados()` devuelve
    vacío: el doble no recuerda nada entre requests.
    """

    def __init__(self, entorno: Entorno = Entorno.LOCAL) -> None:
        if entorno is Entorno.PRODUCTION:
            raise RuntimeError(
                "Las plantillas simuladas no pueden usarse en producción: aprobarían textos "
                "que Meta nunca revisó"
            )

    async def crear(
        self, *, nombre: str, idioma: str, cuerpo: str, ejemplos: Mapping[str, str]
    ) -> RespuestaDePlantilla:
        del nombre, idioma, cuerpo, ejemplos
        return RespuestaDePlantilla(
            meta_plantilla_id=f"simulada-{uuid4()}", estado="APPROVED", categoria=CATEGORIA
        )

    async def editar(
        self, *, meta_plantilla_id: str, cuerpo: str, ejemplos: Mapping[str, str]
    ) -> RespuestaDePlantilla:
        del cuerpo, ejemplos
        return RespuestaDePlantilla(
            meta_plantilla_id=meta_plantilla_id, estado="APPROVED", categoria=CATEGORIA
        )

    @property
    def estados_completos(self) -> bool:
        """No recuerda nada: que una plantilla falte acá no dice que Meta no la tenga."""
        return False

    async def estados(self) -> list[PlantillaEnMeta]:
        return []


class SinCuentaDeMeta:
    """La empresa no conectó WhatsApp (o su credencial no se puede leer): no hay a quién pedirle."""

    async def crear(
        self, *, nombre: str, idioma: str, cuerpo: str, ejemplos: Mapping[str, str]
    ) -> RespuestaDePlantilla:
        del nombre, idioma, cuerpo, ejemplos
        raise CanalNoConectado(SIN_CUENTA)

    async def editar(
        self, *, meta_plantilla_id: str, cuerpo: str, ejemplos: Mapping[str, str]
    ) -> RespuestaDePlantilla:
        del meta_plantilla_id, cuerpo, ejemplos
        raise CanalNoConectado(SIN_CUENTA)

    @property
    def estados_completos(self) -> bool:
        return False

    async def estados(self) -> list[PlantillaEnMeta]:
        raise CanalNoConectado(SIN_CUENTA)


__all__ = [
    "CATEGORIA",
    "PlantillaEnMeta",
    "PlantillasDeMeta",
    "PlantillasSimuladas",
    "RespuestaDePlantilla",
    "SinCuentaDeMeta",
]
