"""Sample used to validate the static analysis pipeline (Etapa 6, activity 2).

This is NOT part of the system: it is the fixture the CI pipeline runs against to
prove it still catches violations of the absolute rules in CLAUDE.md section 3.
This is the corrected version; the previous commit carries the defective one.
"""

import logging
import os
import sqlite3
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import httpx

logger = logging.getLogger(__name__)

IVA_GENERAL = Decimal("0.21")
DOS_DECIMALES = Decimal("0.01")
TIMEOUT_ARCA = httpx.Timeout(10.0, connect=5.0)


class EmisionFallida(Exception):
    """The document could not be issued against ARCA."""


def _clave_del_certificado() -> str:
    """Read the certificate passphrase from the environment. It never lives in code."""
    clave = os.environ.get("ARCA_CERT_PASSWORD")
    if not clave:
        raise EmisionFallida
    return clave


def total_con_iva(neto: Decimal, alicuota: Decimal = IVA_GENERAL) -> Decimal:
    """Add VAT to a net amount, rounding to two decimals with ROUND_HALF_UP."""
    return (neto * (Decimal(1) + alicuota)).quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)


def buscar_comprobante(
    conexion: sqlite3.Connection, empresa_id: str, numero: int
) -> list[tuple[Any, ...]]:
    """Look a document up with a parameterised statement."""
    cursor = conexion.cursor()
    cursor.execute(
        "SELECT * FROM comprobante WHERE empresa_id = ? AND numero = ?",
        (empresa_id, numero),
    )
    return cursor.fetchall()


def emitir(neto: Decimal, empresa_id: str, numero: int) -> dict[str, object]:
    """Issue a document and return its total and issuing timestamp."""
    emitido_en = datetime.now(UTC)
    total = total_con_iva(neto)
    logger.info("emitiendo comprobante", extra={"empresa_id": empresa_id, "total": str(total)})

    try:
        with sqlite3.connect("cheatsheet.db") as conexion:
            buscar_comprobante(conexion, empresa_id, numero)
        respuesta = httpx.post(
            "https://wsaa.afip.gov.ar",
            auth=("cheatsheet", _clave_del_certificado()),
            timeout=TIMEOUT_ARCA,
        )
        respuesta.raise_for_status()
    except (sqlite3.Error, httpx.HTTPError) as exc:
        logger.exception("fallo la emision", extra={"empresa_id": empresa_id})
        raise EmisionFallida from exc

    return {"total": total, "emitido_en": emitido_en}
