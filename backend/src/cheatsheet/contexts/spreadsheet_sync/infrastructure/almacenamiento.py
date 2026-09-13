"""Where an uploaded workbook's bytes live — Cloudflare R2, and its stand-in.

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

from cheatsheet.contexts.spreadsheet_sync.application.ports import ArchivoGuardado
from cheatsheet.platform.settings import Entorno
from cheatsheet.platform.telemetry import obtener_logger

logger = obtener_logger(__name__)


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
        respuesta = await asyncio.to_thread(
            self._cliente.get_object, Bucket=self._bucket, Key=clave
        )
        cuerpo: bytes = await asyncio.to_thread(respuesta["Body"].read)
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
