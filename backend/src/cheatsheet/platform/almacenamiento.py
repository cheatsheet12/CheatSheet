"""Cloudflare R2, and its stand-in. Where bytes live.

Started in `spreadsheet_sync` for uploaded workbooks and promoted here when `billing` had
to store a document's PDF: object storage is platform infrastructure (`docs/architecture.md`
§2, row 12), and rule R3 forbids one context reaching into another's `infrastructure/`. It
is the same move `soap.py` and `wsfe.py` already made in this epic, and for the same
reason — the alternative was a second copy of one adapter.

Two adapters, the same shape the epic 2 integrations already use: a real one and a
simulated one that is **rejected in production**. The reason is the same too — a company
believing its spreadsheet was uploaded when nothing ever left the process is a company
that will wonder why its catalogue never fills.

**`boto3` is imported lazily, inside the constructor.** It is the architected client for
R2 (`docs/architecture.md` §2) and it is a real dependency of this module, but importing
it at module scope would make the whole context unimportable wherever it is absent —
which includes a laptop that has not reinstalled since this unit landed, and every test
that only ever touches the simulator. The failure it produces instead is a sentence naming
the package, at the moment somebody actually configures R2.

**`boto3` is synchronous**, so each call goes through `asyncio.to_thread`. A 25 MB upload
on the event loop would stall every other request in the process for its duration.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import lru_cache

from cheatsheet.platform.settings import AdaptadorDeAlmacenamiento, Entorno, Settings
from cheatsheet.platform.telemetry import obtener_logger

logger = obtener_logger(__name__)


class AlmacenamientoNoDisponible(RuntimeError):
    """The object store could not be reached, or refused. Distinct from "not there".

    The distinction is the whole reason this exception exists: a missing key is a
    `FileNotFoundError` and often an ordinary outcome, while this one means the store
    itself is unhappy. Collapsing them would make an outage look like an empty bucket.
    """


#: The codes S3 and R2 use for a key that is not there. Two, because `get_object` answers
#: `NoSuchKey` and a `head`-style probe answers `404`.
_CODIGOS_DE_INEXISTENTE = frozenset({"NoSuchKey", "404", "NoSuchBucket"})


def _es_inexistente(error: Exception) -> bool:
    """Whether a `botocore` error means "that key is not there".

    Read out of the response dict rather than by importing `botocore.exceptions`: this
    module keeps `boto3` a lazy dependency, and an `except` clause naming a class from it
    would drag the import back to module scope -- which is precisely what the constructor
    below goes out of its way to avoid.
    """
    respuesta = getattr(error, "response", None)
    if not isinstance(respuesta, dict):
        return False
    codigo = str(respuesta.get("Error", {}).get("Code", ""))
    return codigo in _CODIGOS_DE_INEXISTENTE


@dataclass(frozen=True, slots=True)
class ArchivoGuardado:
    """The result of putting bytes in the object store.

    **The ports it satisfies live in the consuming contexts**, not here, which is what
    hexagonal asks for: a port is the consumer's contract. `spreadsheet_sync` and `billing`
    each declare one, they happen to have the same three operations, and this adapter
    structurally satisfies both without either importing the other.
    """

    clave: str
    tamano_bytes: int


@dataclass(frozen=True, slots=True)
class ConfiguracionR2:
    """What R2 needs. All of it from the environment: these are platform credentials."""

    endpoint: str
    bucket: str
    access_key_id: str
    secret_access_key: str

    @property
    def esta_configurado(self) -> bool:
        return all((self.endpoint, self.bucket, self.access_key_id, self.secret_access_key))


class AlmacenamientoR2:
    """`PortAlmacenamientoDeArchivos` against Cloudflare R2."""

    def __init__(self, configuracion: ConfiguracionR2) -> None:
        if not configuracion.esta_configurado:
            raise RuntimeError(
                "R2 no esta configurado: faltan R2_ENDPOINT, R2_BUCKET, "
                "R2_ACCESS_KEY_ID o R2_SECRET_ACCESS_KEY"
            )
        try:
            # The deferred import is the point -- see the module docstring. boto3 ships no
            # stubs, and is listed among the `ignore_missing_imports` modules in
            # pyproject.toml rather than silenced inline: the override is narrow, and an
            # inline ignore would need a different error code depending on whether the
            # package happens to be installed on the machine running mypy.
            import boto3
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on the install
            raise RuntimeError(
                "Falta la dependencia boto3, que es el cliente de Cloudflare R2. "
                "Instalala con: pip install -e backend"
            ) from exc

        self._bucket = configuracion.bucket
        self._cliente = boto3.client(
            "s3",
            endpoint_url=configuracion.endpoint,
            aws_access_key_id=configuracion.access_key_id,
            aws_secret_access_key=configuracion.secret_access_key,
            # R2 ignores the region but the S3 client insists on one being present.
            region_name="auto",
        )
        # Captured at construction, where `boto3` is already imported, so `leer` can name
        # the exception it catches without an `except Exception` -- which `CLAUDE.md` §5
        # forbids -- and without dragging `botocore` up to module scope.
        self._errores_del_cliente: tuple[type[Exception], ...] = (
            self._cliente.exceptions.ClientError,
            OSError,
        )

    async def guardar(
        self, *, clave: str, contenido: bytes, tipo_de_contenido: str
    ) -> ArchivoGuardado:
        await asyncio.to_thread(
            self._cliente.put_object,
            Bucket=self._bucket,
            Key=clave,
            Body=contenido,
            ContentType=tipo_de_contenido,
        )
        # The key, never the content: these bytes are somebody's customer list.
        logger.info("planilla_guardada", clave=clave, tamano=len(contenido))
        return ArchivoGuardado(clave=clave, tamano_bytes=len(contenido))

    async def leer(self, clave: str) -> bytes:
        """Raises `FileNotFoundError` for a missing key, `AlmacenamientoNoDisponible` for
        anything else.

        Translated here rather than left to leak, and the reason is a caller: `billing`
        caches a document's PDF in this store, and for it **both mean the same thing** --
        we do not have the bytes, so render them again. Letting `botocore.ClientError`
        through would force that caller into an `except Exception`, which `CLAUDE.md` §5
        forbids and which would also swallow real bugs.
        """
        try:
            respuesta = await asyncio.to_thread(
                self._cliente.get_object, Bucket=self._bucket, Key=clave
            )
            cuerpo: bytes = await asyncio.to_thread(respuesta["Body"].read)
        except self._errores_del_cliente as exc:
            if _es_inexistente(exc):
                raise FileNotFoundError(clave) from exc
            raise AlmacenamientoNoDisponible(f"No se pudo leer {clave}: {exc}") from exc
        return cuerpo

    async def eliminar(self, clave: str) -> None:
        await asyncio.to_thread(self._cliente.delete_object, Bucket=self._bucket, Key=clave)
        logger.info("planilla_eliminada", clave=clave)


class AlmacenamientoEnMemoria:
    """The stand-in. Keeps the bytes in a dict and opens no socket.

    Enough to walk the whole ingestion flow on a laptop with no R2 bucket, which is the
    same licence `EnviadorDeConsola` and the three simulated integrations already take.
    """

    def __init__(self, entorno: Entorno = Entorno.LOCAL) -> None:
        if entorno is Entorno.PRODUCTION:
            raise RuntimeError(
                "El almacenamiento en memoria no es valido en produccion: "
                "las planillas subidas se perderian al reiniciar el proceso."
            )
        self.archivos: dict[str, bytes] = {}

    async def guardar(
        self, *, clave: str, contenido: bytes, tipo_de_contenido: str
    ) -> ArchivoGuardado:
        del tipo_de_contenido  # Kept in the signature because the port declares it.
        self.archivos[clave] = contenido
        return ArchivoGuardado(clave=clave, tamano_bytes=len(contenido))

    async def leer(self, clave: str) -> bytes:
        if clave not in self.archivos:
            raise FileNotFoundError(clave)
        return self.archivos[clave]

    async def eliminar(self, clave: str) -> None:
        self.archivos.pop(clave, None)


@lru_cache(maxsize=1)
def almacenamiento(settings: Settings) -> AlmacenamientoR2 | AlmacenamientoEnMemoria:
    """The object store, built once per process.

    The in-memory one is cached too, and **has to be**: two instances would be two different
    buckets, and a file written through one would be missing from the other. That matters
    more now than when this lived in `spreadsheet_sync`, because there are two consumers --
    a workbook and a document's PDF share the store, and they must share the same one.
    """
    if settings.almacenamiento_adaptador is AdaptadorDeAlmacenamiento.R2:
        return AlmacenamientoR2(
            ConfiguracionR2(
                endpoint=settings.r2_endpoint,
                bucket=settings.r2_bucket,
                access_key_id=settings.r2_access_key_id,
                secret_access_key=settings.r2_secret_access_key,
            )
        )
    return AlmacenamientoEnMemoria(settings.entorno)
