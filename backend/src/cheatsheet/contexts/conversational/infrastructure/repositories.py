"""Adaptadores PostgreSQL de los cuatro repositorios de `conversational`.

Las convenciones de siempre: mapeo a mano en los dos sentidos para que el dominio no cargue
una dependencia de framework (R1), y `empresa_id` nunca en un `WHERE` porque RLS ya acota.

**La búsqueda por significado es SQL explícito.** `pgvector` provee el operador `<=>`
—distancia coseno— y `1 - (a <=> b)` es la similitud. Se escribe a mano, con parámetros y un
`::vector` explícito, porque mapear la columna pediría una dependencia entera para ahorrar
estas veinte líneas. La consulta ordena por distancia y **no filtra por umbral**: el umbral es
una regla de negocio y la aplica el caso de uso.

**`buscar_por_externo_id` es la idempotencia del webhook de Meta.** Una consulta antes de
gastar un token de LLM: si el mensaje ya se procesó, no hace falta nada más.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.conversational.domain.conversacion import (
    Conversacion,
    EstadoConversacion,
)
from cheatsheet.contexts.conversational.domain.escalamiento import (
    ESTADOS_SIN_AGENTE,
    Escalamiento,
    EstadoEscalamiento,
)
from cheatsheet.contexts.conversational.domain.faq import FAQ, CoincidenciaDeFAQ
from cheatsheet.contexts.conversational.infrastructure.dialogo_json import (
    dialogo_a_json,
    leer_dialogo_guardado,
)
from cheatsheet.contexts.conversational.infrastructure.models import (
    FAQORM,
    ConversacionORM,
    EscalamientoORM,
)
from cheatsheet.shared.empresa import EmpresaId, UsuarioId

#: `<=>` es la distancia coseno de `pgvector`; `1 - distancia` es la similitud.
#:
#: El vector entra como texto y se castea. El literal `[0.1,0.2,…]` **no** se interpola: viaja
#: como parámetro, porque un SQL armado con f-string se le parece a un escáner exactamente a la
#: inyección que no es — y porque acá el contenido sí viene, indirectamente, de lo que escribió
#: un desconocido.
BUSQUEDA_POR_SIGNIFICADO = text(
    """
    SELECT id, 1 - (embedding_vector <=> CAST(:vector AS vector)) AS similitud
    FROM faq
    WHERE embedding_vector IS NOT NULL
    ORDER BY embedding_vector <=> CAST(:vector AS vector)
    LIMIT :limite
    """
)

GUARDAR_VECTOR = text("UPDATE faq SET embedding_vector = CAST(:vector AS vector) WHERE id = :id")


def _como_literal(vector: Sequence[float]) -> str:
    """El formato de texto que `pgvector` acepta: `[1,2,3]`."""
    return "[" + ",".join(f"{float(uno):.8f}" for uno in vector) + "]"


class RepositorioConversacionPostgres:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, conversacion: Conversacion) -> None:
        self._sesion.add(_conversacion_a_fila(conversacion, ConversacionORM()))
        await self._sesion.flush()

    async def guardar(self, conversacion: Conversacion) -> None:
        fila = await self._sesion.get(ConversacionORM, conversacion.id)
        if fila is None:
            raise LookupError(f"La conversación {conversacion.id} no existe para esta empresa")
        _conversacion_a_fila(conversacion, fila)
        await self._sesion.flush()

    async def buscar_por_id(self, conversacion_id: UUID) -> Conversacion | None:
        fila = await self._sesion.get(ConversacionORM, conversacion_id)
        return _conversacion_a_dominio(fila) if fila is not None else None

    async def abierta_de(self, cliente_id: UUID, *, bloquear: bool = False) -> Conversacion | None:
        """El hilo activo de ese cliente. **El más reciente**, si hubiera más de uno.

        No debería haber dos —sólo se abre uno cuando no hay ninguno— pero pedir el último es
        gratis y evita que una carrera deje el sistema contestando sobre un hilo viejo.

        Con `bloquear`, `SELECT … FOR UPDATE` (T10): los mensajes de un mismo hilo se procesan de
        a uno y el segundo lee el diálogo ya consumido. El bloqueo es por fila: no frena a otros
        clientes.
        """
        sentencia = (
            select(ConversacionORM)
            .where(ConversacionORM.cliente_id == cliente_id)
            .where(ConversacionORM.estado == EstadoConversacion.ACTIVA.value)
            .order_by(ConversacionORM.created_at.desc())
            .limit(1)
        )
        if bloquear:
            sentencia = sentencia.with_for_update()
        fila = (await self._sesion.execute(sentencia)).scalar_one_or_none()
        return _conversacion_a_dominio(fila) if fila is not None else None

    async def listar(self, *, solo_escaladas: bool = False) -> list[Conversacion]:
        sentencia = select(ConversacionORM).order_by(
            ConversacionORM.ultimo_mensaje_en.desc().nullslast()
        )
        if solo_escaladas:
            # La bandeja del operador: los hilos con un escalamiento sin resolver. Se resuelve
            # con un `EXISTS` y no trayendo todo a Python, porque la lista de escaladas es
            # chica y la de conversaciones no lo va a ser.
            abiertos = (
                select(EscalamientoORM.conversacion_id)
                .where(EscalamientoORM.estado.in_([uno.value for uno in ESTADOS_SIN_AGENTE]))
                .scalar_subquery()
            )
            sentencia = sentencia.where(ConversacionORM.id.in_(abiertos))
        filas = (await self._sesion.execute(sentencia)).scalars().all()
        return [_conversacion_a_dominio(fila) for fila in filas]


class RepositorioEscalamientoPostgres:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, escalamiento: Escalamiento) -> None:
        self._sesion.add(_escalamiento_a_fila(escalamiento, EscalamientoORM()))
        await self._sesion.flush()

    async def guardar(self, escalamiento: Escalamiento) -> None:
        fila = await self._sesion.get(EscalamientoORM, escalamiento.id)
        if fila is None:
            raise LookupError(f"El escalamiento {escalamiento.id} no existe para esta empresa")
        _escalamiento_a_fila(escalamiento, fila)
        await self._sesion.flush()

    async def buscar_por_id(self, escalamiento_id: UUID) -> Escalamiento | None:
        fila = await self._sesion.get(EscalamientoORM, escalamiento_id)
        return _escalamiento_a_dominio(fila) if fila is not None else None

    async def abierto_de(self, conversacion_id: UUID) -> Escalamiento | None:
        """**La consulta que decide si el agente contesta.** Ver el puerto."""
        sentencia = (
            select(EscalamientoORM)
            .where(EscalamientoORM.conversacion_id == conversacion_id)
            .where(EscalamientoORM.estado.in_([uno.value for uno in ESTADOS_SIN_AGENTE]))
            .order_by(EscalamientoORM.created_at.desc())
            .limit(1)
        )
        fila = (await self._sesion.execute(sentencia)).scalar_one_or_none()
        return _escalamiento_a_dominio(fila) if fila is not None else None

    async def listar_abiertos(self) -> list[Escalamiento]:
        sentencia = (
            select(EscalamientoORM)
            .where(EscalamientoORM.estado.in_([uno.value for uno in ESTADOS_SIN_AGENTE]))
            .order_by(EscalamientoORM.created_at)
        )
        filas = (await self._sesion.execute(sentencia)).scalars().all()
        return [_escalamiento_a_dominio(fila) for fila in filas]


class RepositorioFAQPostgres:
    """Las FAQ, con la búsqueda vectorial escrita a mano. Ver el docstring del módulo."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, faq: FAQ) -> None:
        self._sesion.add(_faq_a_fila(faq, FAQORM(), nueva=True))
        await self._sesion.flush()

    async def guardar(self, faq: FAQ) -> None:
        fila = await self._sesion.get(FAQORM, faq.id)
        if fila is None:
            raise LookupError(f"La FAQ {faq.id} no existe para esta empresa")
        _faq_a_fila(faq, fila)
        await self._sesion.flush()

    async def guardar_vector(self, faq: FAQ, vector: Sequence[float]) -> None:
        await self.guardar(faq)
        await self._sesion.execute(GUARDAR_VECTOR, {"vector": _como_literal(vector), "id": faq.id})

    async def eliminar(self, faq_id: UUID) -> None:
        """HU-E9-04 RN-03: la única baja real del sistema. Ver el puerto."""
        await self._sesion.execute(delete(FAQORM).where(FAQORM.id == faq_id))
        await self._sesion.flush()

    async def buscar_por_id(self, faq_id: UUID) -> FAQ | None:
        fila = await self._sesion.get(FAQORM, faq_id)
        return _faq_a_dominio(fila) if fila is not None else None

    async def listar(self) -> list[FAQ]:
        sentencia = select(FAQORM).order_by(FAQORM.created_at)
        filas = (await self._sesion.execute(sentencia)).scalars().all()
        return [_faq_a_dominio(fila) for fila in filas]

    async def buscar_por_significado(
        self, vector: Sequence[float], *, limite: int = 3
    ) -> list[CoincidenciaDeFAQ]:
        filas = (
            await self._sesion.execute(
                BUSQUEDA_POR_SIGNIFICADO, {"vector": _como_literal(vector), "limite": limite}
            )
        ).all()
        coincidencias: list[CoincidenciaDeFAQ] = []
        for faq_id, similitud in filas:
            faq = await self.buscar_por_id(faq_id)
            if faq is not None:
                coincidencias.append(CoincidenciaDeFAQ(faq=faq, similitud=float(similitud)))
        return coincidencias

    async def pendientes_de_indexar(self) -> list[FAQ]:
        sentencia = select(FAQORM).where(FAQORM.embedding_obsoleto.is_(True))
        filas = (await self._sesion.execute(sentencia)).scalars().all()
        return [_faq_a_dominio(fila) for fila in filas]


# -- mapeos ---------------------------------------------------------------------------


def _conversacion_a_dominio(fila: ConversacionORM) -> Conversacion:
    return Conversacion(
        id=fila.id,
        empresa_id=EmpresaId(fila.empresa_id),
        cliente_id=fila.cliente_id,
        estado=EstadoConversacion(fila.estado),
        contador=fila.contador,
        ventana_maximo=fila.ventana_maximo,
        ultimo_mensaje_en=fila.ultimo_mensaje_en,
        created_at=fila.created_at,
        dialogo=leer_dialogo_guardado(fila.dialogo, conversacion_id=fila.id),
    )


def _conversacion_a_fila(conversacion: Conversacion, fila: ConversacionORM) -> ConversacionORM:
    fila.id = conversacion.id
    fila.empresa_id = conversacion.empresa_id
    fila.cliente_id = conversacion.cliente_id
    fila.estado = conversacion.estado.value
    fila.contador = conversacion.contador
    fila.ventana_maximo = conversacion.ventana_maximo
    fila.ultimo_mensaje_en = conversacion.ultimo_mensaje_en
    fila.created_at = conversacion.created_at or _ahora(conversacion.ultimo_mensaje_en)
    fila.dialogo = None if conversacion.dialogo is None else dialogo_a_json(conversacion.dialogo)
    return fila


def _escalamiento_a_dominio(fila: EscalamientoORM) -> Escalamiento:
    return Escalamiento(
        id=fila.id,
        conversacion_id=fila.conversacion_id,
        empresa_id=EmpresaId(fila.empresa_id),
        motivo=fila.motivo,
        estado=EstadoEscalamiento(fila.estado),
        usuario_asignado_id=(
            UsuarioId(fila.usuario_asignado_id) if fila.usuario_asignado_id else None
        ),
        created_at=fila.created_at,
        updated_at=fila.updated_at,
    )


def _escalamiento_a_fila(escalamiento: Escalamiento, fila: EscalamientoORM) -> EscalamientoORM:
    fila.id = escalamiento.id
    fila.conversacion_id = escalamiento.conversacion_id
    fila.empresa_id = escalamiento.empresa_id
    fila.usuario_asignado_id = escalamiento.usuario_asignado_id
    fila.motivo = escalamiento.motivo
    fila.estado = escalamiento.estado.value
    fila.created_at = escalamiento.created_at or _ahora(escalamiento.updated_at)
    fila.updated_at = escalamiento.updated_at or fila.created_at
    return fila


def _faq_a_dominio(fila: FAQORM) -> FAQ:
    return FAQ(
        id=fila.id,
        empresa_id=EmpresaId(fila.empresa_id),
        pregunta=fila.pregunta,
        respuesta=fila.respuesta,
        categoria_id=fila.categoria_id,
        embedding_modelo_version=fila.embedding_modelo_version,
        embedding_obsoleto=fila.embedding_obsoleto,
        usos_anteriores=fila.usos_anteriores,
        created_at=fila.created_at,
        updated_at=fila.updated_at,
        editada_en=fila.editada_en,
        seguimiento_desde=fila.seguimiento_desde,
    )


def _faq_a_fila(faq: FAQ, fila: FAQORM, *, nueva: bool = False) -> FAQORM:
    fila.id = faq.id
    fila.empresa_id = faq.empresa_id
    fila.categoria_id = faq.categoria_id
    fila.pregunta = faq.pregunta
    fila.respuesta = faq.respuesta
    fila.embedding_modelo_version = faq.embedding_modelo_version
    fila.embedding_obsoleto = faq.embedding_obsoleto
    fila.editada_en = faq.editada_en
    fila.created_at = faq.created_at or _ahora(faq.updated_at)
    fila.updated_at = faq.updated_at or fila.created_at
    if nueva:  # la línea de base y el seguimiento solo los escribe el alta (ADR-0012)
        fila.usos_anteriores = faq.usos_anteriores
        fila.seguimiento_desde = faq.seguimiento_desde or fila.created_at
    return fila


def _ahora(alternativa: datetime | None) -> datetime:
    """El instante que se guarda cuando el agregado no trajo uno.

    Prefiere el que sí tenga a inventar uno: un `created_at` puesto por el reloj del proceso
    es la clase de dato que discrepa del resto de la transacción por milisegundos y que
    después nadie entiende.
    """
    return alternativa if alternativa is not None else datetime.now(tz=UTC)


__all__ = [
    "RepositorioConversacionPostgres",
    "RepositorioEscalamientoPostgres",
    "RepositorioFAQPostgres",
]
