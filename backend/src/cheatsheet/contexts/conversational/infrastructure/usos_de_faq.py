"""Adaptador PostgreSQL de los usos de FAQ (ADR-0012).

Tres consultas, todas con SQL explícito y literal. `empresa_id` no aparece en ningún `WHERE`:
RLS ya acota a la empresa de la transacción, como en el resto de los repositorios.

**Los límites de los meses llegan como instantes UTC calculados en Python** (`MesCalendario`):
la consulta compara contra un índice y la lógica del mes se prueba sin PostgreSQL.

**`registrar` es `INSERT … ON CONFLICT (mensaje_id) DO NOTHING`**: un mensaje es a lo sumo un
uso. No lee ni escribe la fila de `faq`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.conversational.domain.uso_de_faq import ConteoDeUsos, UsoDeFAQ
from cheatsheet.shared.zona_horaria import MesCalendario

REGISTRAR = text(
    """
    INSERT INTO faq_uso (id, empresa_id, faq_id, mensaje_id, usado_en)
    VALUES (:id, :empresa_id, :faq_id, :mensaje_id, :usado_en)
    ON CONFLICT (mensaje_id) DO NOTHING
    """
)

#: Una sola consulta para todo el listado. Las FAQ borradas (`faq_id IS NULL`) no se listan.
CONTEOS = text(
    """
    SELECT
        faq_id,
        count(*) FILTER (WHERE usado_en >= :inicio AND usado_en < :fin) AS este_mes,
        count(*) FILTER (
            WHERE usado_en >= :inicio_anterior AND usado_en < :inicio
        ) AS mes_anterior,
        count(*) AS total
    FROM faq_uso
    WHERE faq_id IS NOT NULL
    GROUP BY faq_id
    """
)

CONTAR_DE_UNA_FAQ = text(
    "SELECT count(*) FROM faq_uso WHERE faq_id = :faq_id AND usado_en >= :desde AND usado_en < :hasta"
)

CONTAR_DE_LA_EMPRESA = text(
    "SELECT count(*) FROM faq_uso WHERE usado_en >= :desde AND usado_en < :hasta"
)


class RepositorioUsosDeFAQPostgres:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def registrar(self, uso: UsoDeFAQ) -> None:
        await self._sesion.execute(
            REGISTRAR,
            {
                "id": uso.id,
                "empresa_id": uso.empresa_id,
                "faq_id": uso.faq_id,
                "mensaje_id": uso.mensaje_id,
                "usado_en": uso.usado_en,
            },
        )

    async def conteos(self, mes: MesCalendario) -> dict[UUID, ConteoDeUsos]:
        resultado = await self._sesion.execute(
            CONTEOS,
            {"inicio": mes.inicio, "fin": mes.fin, "inicio_anterior": mes.anterior().inicio},
        )
        return {
            fila.faq_id: ConteoDeUsos(
                este_mes=int(fila.este_mes),
                mes_anterior=int(fila.mes_anterior),
                desde_el_seguimiento=int(fila.total),
            )
            for fila in resultado
        }

    async def contar(self, *, desde: datetime, hasta: datetime, faq_id: UUID | None) -> int:
        if faq_id is None:
            resultado = await self._sesion.execute(
                CONTAR_DE_LA_EMPRESA, {"desde": desde, "hasta": hasta}
            )
        else:
            resultado = await self._sesion.execute(
                CONTAR_DE_UNA_FAQ, {"faq_id": faq_id, "desde": desde, "hasta": hasta}
            )
        return int(resultado.scalar_one())


__all__ = ["RepositorioUsosDeFAQPostgres"]
