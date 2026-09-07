"""`PortInterprete` — el modelo que lee lo que escribió un desconocido.

Dos adaptadores, la misma forma que toda integración de este repositorio: uno real y uno
simulado que `Settings` rechaza en producción.

**Lo que el modelo puede hacer: devolver una etiqueta y un número.** No tiene herramientas, no
tiene acceso a la base, no puede reservar ni cobrar. Es la decisión **D38** y es la razón por
la que un prompt injection acá no llega a ninguna parte: aunque el atacante convenza al modelo
de cualquier cosa, lo único que sale de esta clase es un `Lectura`, y `Lectura` no puede hacer
nada.

**Tres defensas, y ninguna se apoya en el prompt:**

1. **El mensaje va delimitado y declarado como dato.** El prompt lo dice; el prompt es la
   defensa más débil de las tres y está primera porque es la única que puede mejorar la
   respuesta en lugar de sólo contenerla.
2. **El esquema de salida es cerrado.** `intencion` es un `enum` de cinco valores en el JSON
   Schema que la API hace cumplir. Un modelo convencido de escribir cualquier otra cosa no
   puede: no hay forma en el esquema.
3. **La respuesta se valida de nuevo acá.** `CLAUDE.md` §5: la salida de un modelo es entrada
   no confiable como cualquier formulario, y una garantía que no comprobamos nosotros es una
   garantía que le estamos creyendo a un proveedor.

**Fallar es un estado previsto.** Timeout, rechazo, respuesta mal formada, sin API key: todos
devuelven confianza cero, que el caso de uso convierte en un escalamiento. El canal nunca se
queda sin contestar por una caída ajena — contesta una persona.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from anthropic.types import MessageParam, OutputConfigParam

from cheatsheet.contexts.conversational.application.ports import Lectura
from cheatsheet.contexts.conversational.domain.conversacion import Intencion
from cheatsheet.platform.settings import Entorno
from cheatsheet.platform.telemetry import obtener_logger

logger = obtener_logger(__name__)

#: Los prompts viven en archivos versionados, nunca embebidos en la lógica (`CLAUDE.md` §5).
DIRECTORIO_DE_PROMPTS = Path(__file__).parent / "prompts"

#: La forma en la que el modelo tiene que contestar. Se declara a la API **y** se comprueba a
#: la vuelta. `intencion` es un enum cerrado: es la segunda de las tres defensas.
ESQUEMA_DE_LECTURA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["intencion", "confianza", "resumen"],
    "properties": {
        "intencion": {"type": "string", "enum": [uno.value for uno in Intencion]},
        "confianza": {"type": "number", "minimum": 0, "maximum": 1},
        "resumen": {"type": "string", "maxLength": 200},
    },
}

#: Cuánto historial se le manda. Seis mensajes son tres vueltas de conversación: alcanza para
#: entender un «sí, ese» y no tanto como para que un mensaje viejo pese más que el actual.
#:
#: También acota el gasto: el historial entero de un hilo largo es plata por mensaje.
MENSAJES_DE_CONTEXTO = 6

#: Lo que se devuelve cuando el modelo no contestó o contestó cualquier cosa. Confianza cero,
#: que el caso de uso convierte en un escalamiento.
SIN_LECTURA = Lectura(intencion=Intencion.DESCONOCIDA, confianza=0.0)


def _leer_prompt(nombre: str) -> str:
    return (DIRECTORIO_DE_PROMPTS / nombre).read_text(encoding="utf-8")


def envolver(texto: str) -> str:
    """El mensaje del cliente, delimitado y declarado como dato.

    Los delimitadores se cierran siempre, incluso si el texto los contiene: lo que hace que
    esto sirva no es que sean únicos, es que el esquema de salida no deja escapar nada aunque
    el modelo se confunda. La delimitación mejora la respuesta; no es lo que la contiene.
    """
    return f"<mensaje_del_cliente>\n{texto}\n</mensaje_del_cliente>"


@dataclass(frozen=True, slots=True)
class ConfiguracionDelInterprete:
    api_key: str
    modelo: str
    timeout_segundos: float
    max_tokens: int
    #: Clasificar una frase corta es barato. El épico 4 usa `low` para lo mismo.
    esfuerzo: Literal["low", "medium", "high", "xhigh", "max"] = "low"

    @property
    def esta_configurado(self) -> bool:
        return bool(self.api_key and self.modelo)


class InterpreteSimulado:
    """El doble: clasifica por palabras clave, sin red y sin costo.

    **Rechazado en producción**, como los demás simulados. Una empresa cuyo agente clasifica
    por subcadenas contesta mal a cualquiera que no escriba como el doble espera.

    Las reglas son deliberadamente simples y **conservadoras**: cuando ninguna aplica devuelve
    confianza cero, que escala. Un doble que fingiera entender todo haría que los tests del
    caso de uso pasaran sin ejercitar nunca el camino del escalamiento, que es el que importa.
    """

    PALABRAS: tuple[tuple[Intencion, tuple[str, ...]], ...] = (
        (Intencion.TURNO, ("turno", "reservar", "agendar", "cita", "cancelar")),
        (Intencion.PAGO, ("pagar", "pago", "debo", "deuda", "transferi", "transferí")),
        (Intencion.FAQ, ("precio", "cuanto", "cuánto", "horario", "direccion", "dirección")),
    )

    def __init__(self, entorno: Entorno = Entorno.LOCAL) -> None:
        if entorno is Entorno.PRODUCTION:
            raise RuntimeError(
                "El intérprete simulado no puede usarse en producción: clasifica por palabras "
                "clave y le contestaría cualquier cosa a un cliente real"
            )

    async def leer(self, texto: str, *, historial: Sequence[str] = ()) -> Lectura:
        del historial
        normalizado = texto.lower()
        for intencion, palabras in self.PALABRAS:
            if any(palabra in normalizado for palabra in palabras):
                return Lectura(intencion=intencion, confianza=0.9, resumen=texto[:200])
        return SIN_LECTURA


class InterpreteAnthropic:
    """`PortInterprete` contra Claude (ADR-0007). Ver el docstring del módulo."""

    def __init__(self, configuracion: ConfiguracionDelInterprete) -> None:
        if not configuracion.esta_configurado:
            raise RuntimeError(
                "El intérprete no está configurado: faltan ANTHROPIC_API_KEY o LLM_MODELO"
            )
        try:
            # Diferido por lo mismo que en el épico 4: el contexto tiene que seguir siendo
            # importable donde el paquete no está, y los tests sólo tocan el simulado.
            import anthropic
        except ModuleNotFoundError as exc:  # pragma: no cover - depende de la instalación
            raise RuntimeError(
                "Falta la dependencia anthropic, que es el cliente del modelo (ADR-0007). "
                "Instalala con: pip install -e backend"
            ) from exc

        self._config = configuracion
        # La jerarquía de errores del SDK, capturada acá porque el import es diferido.
        # `AnthropicError` es la base de todo lo que el cliente levanta, así que esto es un
        # conjunto de excepciones nombrado y no el `except Exception` que `CLAUDE.md` §5
        # prohíbe.
        self._errores: tuple[type[Exception], ...] = (anthropic.AnthropicError,)
        self._cliente = anthropic.AsyncAnthropic(
            api_key=configuracion.api_key,
            # Explícito, como pide `CLAUDE.md` §5: el default del SDK son diez minutos, y del
            # otro lado hay alguien esperando una respuesta de WhatsApp.
            timeout=configuracion.timeout_segundos,
        )

    async def leer(self, texto: str, *, historial: Sequence[str] = ()) -> Lectura:
        if not texto.strip():
            return SIN_LECTURA

        salida: OutputConfigParam = {
            "effort": self._config.esfuerzo,
            "format": {"type": "json_schema", "schema": ESQUEMA_DE_LECTURA},
        }
        mensajes: list[MessageParam] = [
            {"role": "user", "content": _con_contexto(texto, historial)}
        ]

        try:
            respuesta = await self._cliente.messages.create(
                model=self._config.modelo,
                max_tokens=self._config.max_tokens,
                system=_leer_prompt("intencion.md"),
                output_config=salida,
                messages=mensajes,
            )
        except self._errores:
            # Toda caída ajena tiene la misma respuesta: confianza cero, que escala. Lo que
            # **no** se atrapa es igual de deliberado — un error nuestro (un keyword mal
            # escrito, un prompt que no existe) sale como el 500 que es, en vez de esconderse
            # detrás de un escalamiento que parece una caída del proveedor.
            logger.warning("interprete_sin_respuesta")
            return SIN_LECTURA

        if getattr(respuesta, "stop_reason", None) == "refusal":
            # Un rechazo es un 200 con `stop_reason == "refusal"`, no una excepción. Leer
            # `.content` sin comprobarlo es cómo un rechazo se vuelve un IndexError en
            # producción.
            logger.warning("interprete_rechazo_el_pedido")
            return SIN_LECTURA

        return _interpretar(respuesta)


def _con_contexto(texto: str, historial: Sequence[str]) -> str:
    """El mensaje a clasificar, con las últimas vueltas del hilo si las hay.

    El historial también va delimitado: son mensajes que escribió la misma persona, así que
    tienen exactamente el mismo estatus de dato no confiable que el mensaje actual.
    """
    if not historial:
        return envolver(texto)
    previos = "\n".join(envolver(uno) for uno in historial[-MENSAJES_DE_CONTEXTO:])
    return f"<historial>\n{previos}\n</historial>\n\n{envolver(texto)}"


def _interpretar(respuesta: Any) -> Lectura:
    """La tercera defensa: revalidar lo que el esquema ya debería haber garantizado.

    Un valor fuera del enum, una confianza fuera de rango o un JSON roto devuelven `SIN_LECTURA`
    en lugar de propagarse. La API declara el esquema; esto comprueba que lo haya cumplido.
    """
    try:
        bloque = respuesta.content[0]
        datos = json.loads(getattr(bloque, "text", "") or "{}")
    except (AttributeError, IndexError, TypeError, json.JSONDecodeError):
        logger.warning("interprete_respondio_algo_ilegible")
        return SIN_LECTURA

    crudo = datos.get("intencion")
    if not isinstance(crudo, str) or crudo not in Intencion.__members__:
        logger.warning("interprete_devolvio_una_intencion_desconocida")
        return SIN_LECTURA

    confianza = datos.get("confianza")
    if not isinstance(confianza, int | float) or not 0.0 <= float(confianza) <= 1.0:
        logger.warning("interprete_devolvio_una_confianza_invalida")
        return SIN_LECTURA

    resumen = datos.get("resumen")
    return Lectura(
        intencion=Intencion[crudo],
        confianza=float(confianza),
        resumen=resumen[:200] if isinstance(resumen, str) else "",
    )


__all__ = [
    "ESQUEMA_DE_LECTURA",
    "SIN_LECTURA",
    "ConfiguracionDelInterprete",
    "InterpreteAnthropic",
    "InterpreteSimulado",
    "envolver",
]
