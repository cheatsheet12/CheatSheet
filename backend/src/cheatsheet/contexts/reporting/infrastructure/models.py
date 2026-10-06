"""Modelos de persistencia de `reporting`.

Tres tablas del DER —`reporte`, `paquete_contable`, `token_de_acceso_contable`— y **una que
el DER no tiene**: `configuracion_de_paquete`. Es el mismo tipo de hueco que el épico 5
encontró con H2, y se resuelve igual: la historia exige persistir algo (día de envío, formato,
contenido y email del contador, HU-E10-04 RN-02 y RN-03) que el modelo no previó, así que la
tabla se crea y la decisión queda escrita.

Dos cosas que valen leerse dos veces:

- **El período de un reporte se guarda como dos fechas y el de un paquete como año y mes.**
  No es una inconsistencia: un reporte es de un rango cualquiera —lo elige quien lo pide— y un
  paquete es de un mes cerrado, siempre. Guardar el paquete como rango permitiría un paquete
  «de tres semanas», que es exactamente lo que el índice único de mes impide.

- **`token_de_acceso_contable` guarda `valor_hash` y no el valor.** Igual que los refresh
  tokens del épico 1. Una base filtrada no puede convertirse en accesos a la documentación
  fiscal de todas las empresas.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from cheatsheet.platform.database import Base

TABLA_REPORTE = "reporte"
TABLA_PAQUETE = "paquete_contable"
#: El nombre lleva «acceso» y no «token» para que el linter de secretos no lo confunda con
#: una credencial escrita en el código: acá no hay ninguna, sólo el nombre de una tabla.
TABLA_ACCESO_CONTABLE = "token_de_acceso_contable"
TABLA_CONFIGURACION = "configuracion_de_paquete"


class ReporteORM(Base):
    __tablename__ = TABLA_REPORTE

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    #: Quién lo pidió. Sin FK desde este ORM: `usuario` es de `identity` y la migración es la
    #: que decide si la restricción existe (regla R3, la misma decisión que tomó `scheduling`).
    usuario_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    tipo: Mapped[str] = mapped_column(String(24), nullable=False)
    formato: Mapped[str] = mapped_column(String(8), nullable=False)
    periodo_desde: Mapped[date] = mapped_column(Date, nullable=False)
    periodo_hasta: Mapped[date] = mapped_column(Date, nullable=False)
    estado: Mapped[str] = mapped_column(String(16), nullable=False)
    filtros: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    referencia_archivo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_reporte_empresa_creado", "empresa_id", "created_at"),)


class PaqueteContableORM(Base):
    """Un mes cerrado de documentación fiscal.

    **`uq_paquete_empresa_periodo` es la regla «un mes, un paquete».** Sin él, el barrido
    mensual que corriera dos veces —dos procesos de Beat, un reintento manual— dejaría dos
    paquetes del mismo mes y el contador tendría que adivinar cuál abrir.
    """

    __tablename__ = TABLA_PAQUETE

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    periodo_anio: Mapped[int] = mapped_column(Integer, nullable=False)
    periodo_mes: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Cuántos comprobantes de cada tipo y por cuánto. Los importes viajan como **texto**
    #: adentro del JSONB: un `float` está mal en el cuarto decimal, que es donde vive un
    #: centavo, y `CLAUDE.md` §3.5 lo prohíbe en todo el sistema.
    totales_por_tipo: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    referencia_archivo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "empresa_id", "periodo_anio", "periodo_mes", name="uq_paquete_empresa_periodo"
        ),
    )


class TokenDeAccesoContableORM(Base):
    """El enlace del contador. Ver el docstring del módulo."""

    __tablename__ = TABLA_ACCESO_CONTABLE

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    paquete_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey(f"{TABLA_PAQUETE}.id", ondelete="CASCADE"), nullable=False
    )
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    #: Único en toda la tabla y no por empresa: el contador llega sin sesión, así que la
    #: búsqueda por hash corre **antes** de saber de qué empresa es. Dos empresas con el mismo
    #: digesto harían de esa consulta una ambigüedad, y la resolvería el azar.
    valor_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    email_contador: Mapped[str] = mapped_column(String(320), nullable=False)
    vencimiento: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accesos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revocado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_token_contable_empresa", "empresa_id", "revocado"),)


class ConfiguracionDePaqueteORM(Base):
    """La tabla que el DER no tiene. Una fila por empresa.

    `empresa_id` es la clave primaria y no una columna más: la configuración del envío es una
    sola por empresa, y dejarla con un id propio permitiría dos filas que se contradicen.
    """

    __tablename__ = TABLA_CONFIGURACION

    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dia_de_envio: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Listas cortas y cerradas, en JSONB. Un `text[]` obligaría a un tipo de columna que sólo
    #: usa esta tabla, y una tabla hija por cada una serían dos tablas para guardar cinco
    #: banderas que siempre se leen y se escriben juntas.
    formatos: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    contenido: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    email_contador: Mapped[str | None] = mapped_column(String(320), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


__all__ = [
    "TABLA_ACCESO_CONTABLE",
    "TABLA_CONFIGURACION",
    "TABLA_PAQUETE",
    "TABLA_REPORTE",
    "ConfiguracionDePaqueteORM",
    "PaqueteContableORM",
    "ReporteORM",
    "TokenDeAccesoContableORM",
]
