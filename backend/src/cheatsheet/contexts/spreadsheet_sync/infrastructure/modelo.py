"""`PortModeloDeLenguaje` — the first LLM of the system (ADR-0007, HU-E3-01 RN-01).

Two adapters, the same shape as every other integration in this repository: a real one and
a simulated one that `Settings` refuses in production.

**What the model is allowed to see: column names, and nothing else.** Decision D12 of the
units map. HU-E3-02 shows «un ejemplo de dato» per column on the review screen, which
invites sending sample rows so the model can infer better — those rows are real customers'
names, CUITs, phones and addresses, and `CLAUDE.md` §3.6 forbids it without anonymisation.
The sample is read from the sheet and rendered on screen **without passing through here**.
The header fingerprint of RN-02 is computed over the same column names, so reusing a stored
mapping does not leak anything either.

**The answer is validated twice.** The request declares the JSON Schema through
`output_config.format`, so the API constrains the shape; then `_interpretar` validates it
again before anything reads it. That is `CLAUDE.md` §5: a model response is untrusted input,
exactly like a submitted form, and a guarantee we did not check ourselves is one we are
taking on trust from a vendor.

**Failing is a designed state.** Timeout, refusal, a malformed answer, no API key — all of
them return an empty proposal, which the use case turns into «every column Sin asignar» and
the user maps by hand. HU-E3-01 RN-03 already draws that screen. The ingestion is never
blocked by somebody else's outage.
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    # Types only. Importing these at runtime would defeat the deferred import below --
    # the module has to stay importable where the package is absent.
    from anthropic.types import MessageParam, OutputConfigParam

from cheatsheet.contexts.spreadsheet_sync.application.ports import Asignacion
from cheatsheet.platform.settings import Entorno
from cheatsheet.platform.telemetry import obtener_logger

logger = obtener_logger(__name__)

#: Prompts live in versioned files, never inline in business logic (`CLAUDE.md` §5).
DIRECTORIO_DE_PROMPTS = Path(__file__).parent / "prompts"

#: The shape the model must answer in. Declared to the API *and* checked on the way back.
ESQUEMA_DE_MAPEO: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["asignaciones"],
    "properties": {
        "asignaciones": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["columna", "atributo", "confianza"],
                "properties": {
                    "columna": {"type": "string"},
                    # Null is a real answer: «I do not know what this column is» is more
                    # useful than a guess, and RN-03 already has a state for it.
                    "atributo": {"type": ["string", "null"]},
                    "confianza": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        }
    },
}


@dataclass(frozen=True, slots=True)
class ConfiguracionDelModelo:
    api_key: str
    modelo: str
    timeout_segundos: float
    max_tokens: int
    #: ADR-0007: header mapping is a simple classification and runs cheap. The knob is
    #: here rather than hardcoded because epic 8's agent will need more. The literal is
    #: written out rather than imported from the SDK so this dataclass carries no runtime
    #: dependency on it.
    esfuerzo: Literal["low", "medium", "high", "xhigh", "max"] = "low"

    @property
    def esta_configurado(self) -> bool:
        return bool(self.api_key and self.modelo)


def _leer_prompt(nombre: str) -> str:
    return (DIRECTORIO_DE_PROMPTS / nombre).read_text(encoding="utf-8")


class ModeloDeLenguajeAnthropic:
    """`PortModeloDeLenguaje` against Claude (ADR-0007)."""

    def __init__(self, configuracion: ConfiguracionDelModelo) -> None:
        if not configuracion.esta_configurado:
            raise RuntimeError(
                "El modelo de lenguaje no esta configurado: faltan ANTHROPIC_API_KEY o LLM_MODELO"
            )
        try:
            # Deferred for the same reason as boto3 in `almacenamiento.py`: the context
            # must stay importable where the package is absent, and every test only ever
            # touches the simulator.
            import anthropic
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on the install
            raise RuntimeError(
                "Falta la dependencia anthropic, que es el cliente del modelo (ADR-0007). "
                "Instalala con: pip install -e backend"
            ) from exc

        self._config = configuracion
        # The SDK's own error hierarchy, captured here because the import is deferred and
        # the module is not in scope at the call site. `AnthropicError` is the base of
        # every failure the client raises -- connection, timeout, 4xx, 5xx -- so this is a
        # named exception set and not the blanket `except Exception` CLAUDE.md section 5
        # forbids. `json` and attribute errors from a malformed answer are handled where
        # the answer is read, not here.
        self._errores_del_cliente: tuple[type[Exception], ...] = (anthropic.AnthropicError,)
        self._cliente = anthropic.AsyncAnthropic(
            api_key=configuracion.api_key,
            # Explicit, as CLAUDE.md section 5 requires: the SDK default is ten minutes,
            # and the review screen of PAN-ING-02 cannot wait that long.
            timeout=configuracion.timeout_segundos,
        )

    async def proponer_mapeo(
        self, *, columnas: tuple[str, ...], atributos: tuple[str, ...]
    ) -> tuple[Asignacion, ...]:
        if not columnas:
            return ()

        salida: OutputConfigParam = {
            "effort": self._config.esfuerzo,
            "format": {"type": "json_schema", "schema": ESQUEMA_DE_MAPEO},
        }
        # Column names and the destination vocabulary. No rows -- decision D12.
        mensajes: list[MessageParam] = [
            {
                "role": "user",
                "content": json.dumps(
                    {"columnas": list(columnas), "atributos": list(atributos)},
                    ensure_ascii=False,
                ),
            }
        ]

        try:
            respuesta = await self._cliente.messages.create(
                model=self._config.modelo,
                max_tokens=self._config.max_tokens,
                system=_leer_prompt("mapeo_de_encabezados.md"),
                output_config=salida,
                messages=mensajes,
            )
        except self._errores_del_cliente as exc:
            # Every failure of somebody else's service has the same answer here: propose
            # nothing, let the user map by hand, never block the ingestion. What is *not*
            # caught is as deliberate -- a bug in our own request (a wrong keyword, a
            # prompt file that does not exist) raises a `TypeError` or an `OSError` and
            # surfaces as the 500 it is, instead of hiding behind an empty mapping that
            # looks like a model outage.
            #
            # The detail logged here is never the empresa's data -- D12 keeps rows out of
            # the model entirely, so `exc.body` is only Anthropic's own complaint about
            # the shape of our request (columns=len(columnas), never their names).
            logger.warning(
                "modelo_sin_respuesta_para_el_mapeo",
                columnas=len(columnas),
                codigo=getattr(exc, "status_code", None),
                mensaje=getattr(exc, "message", str(exc)),
                cuerpo=str(getattr(exc, "body", None))[:2000],
            )
            return ()

        # A refusal is a 200 with `stop_reason == "refusal"`, not an exception. Column
        # headers will not trigger one, but reading `.content` without checking is how a
        # refusal becomes an IndexError in production.
        if getattr(respuesta, "stop_reason", None) == "refusal":
            logger.warning("modelo_rechazo_el_pedido_de_mapeo")
            return ()

        return _interpretar(respuesta, columnas=columnas, atributos=atributos)


def _interpretar(
    respuesta: Any, *, columnas: tuple[str, ...], atributos: tuple[str, ...]
) -> tuple[Asignacion, ...]:
    """The second validation. Anything that does not fit is dropped, never guessed.

    Three things are checked that the schema cannot: that the column is one we asked
    about, that the attribute is one we offered, and that the score parses as a `Decimal`.
    A model that invents a destination attribute would otherwise write into a field that
    does not exist, and the row that discovers it is row one of forty thousand.
    """
    texto = next(
        (bloque.text for bloque in getattr(respuesta, "content", []) if bloque.type == "text"),
        None,
    )
    if texto is None:
        return ()
    try:
        cuerpo = json.loads(texto)
        crudas = cuerpo["asignaciones"]
    except (json.JSONDecodeError, KeyError, TypeError):
        logger.warning("respuesta_del_modelo_no_valida_contra_el_esquema")
        return ()

    validas: list[Asignacion] = []
    for cruda in crudas:
        try:
            columna = str(cruda["columna"])
            atributo = cruda["atributo"]
            score = Decimal(str(cruda["confianza"]))
        except (KeyError, TypeError, InvalidOperation):
            continue
        if columna not in columnas:
            continue
        if atributo is not None and atributo not in atributos:
            # An invented attribute is dropped rather than corrected: leaving the column
            # unassigned costs one manual decision, and the alternative writes a CUIT
            # into whatever field the name happened to resemble.
            logger.info("el_modelo_propuso_un_atributo_inexistente", atributo=str(atributo))
            continue
        if not Decimal("0") <= score <= Decimal("1"):
            continue
        validas.append(Asignacion(columna=columna, atributo=atributo, score=score))

    return tuple(validas)


class ModeloDeLenguajeSimulado:
    """The stand-in: string similarity, no socket, deterministic.

    It is the alternative ADR-0007 rejected as *the* solution and kept as the simulator —
    it handles `Nombre` -> `nombre` and fails on `Razon Soc.`, which is exactly the shape
    of a stand-in: enough to walk the flow on a laptop, obviously not enough to ship.

    **Rejected in production**, like every other simulator here: a company whose mapping
    was guessed by string distance would get a catalogue that looks plausible and is wrong.
    """

    #: Deliberately below `UMBRAL_CONFIANZA_ALTA`: a similarity match is never «Alta», so
    #: a local run shows the review state the real screen shows.
    TECHO_DE_SIMILITUD = Decimal("0.88")

    def __init__(self, entorno: Entorno = Entorno.LOCAL) -> None:
        if entorno is Entorno.PRODUCTION:
            raise RuntimeError(
                "El modelo de lenguaje simulado no es valido en produccion: "
                "el mapeo se adivinaria por parecido de texto."
            )

    async def proponer_mapeo(
        self, *, columnas: tuple[str, ...], atributos: tuple[str, ...]
    ) -> tuple[Asignacion, ...]:
        propuestas: list[Asignacion] = []
        for columna in columnas:
            normalizada = _normalizar(columna)
            mejor, score = _mas_parecido(normalizada, atributos)
            propuestas.append(
                Asignacion(
                    columna=columna,
                    atributo=mejor if score > Decimal("0.5") else None,
                    score=min(score, self.TECHO_DE_SIMILITUD),
                )
            )
        return tuple(propuestas)


def _normalizar(texto: str) -> str:
    reemplazos = str.maketrans("áéíóúüñ", "aeiouun")
    return texto.strip().lower().translate(reemplazos).replace("_", " ").replace(".", "")


def _mas_parecido(columna: str, atributos: tuple[str, ...]) -> tuple[str | None, Decimal]:
    mejor: str | None = None
    mejor_score = Decimal("0")
    for atributo in atributos:
        ratio = difflib.SequenceMatcher(None, columna, _normalizar(atributo)).ratio()
        score = Decimal(str(round(ratio, 4)))
        if score > mejor_score:
            mejor, mejor_score = atributo, score
    return mejor, mejor_score
