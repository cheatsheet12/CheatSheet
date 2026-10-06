"""Los casos de uso de las respuestas frecuentes (HU-E9-04).

**Sólo el Administrador** las administra, que es lo que dice la historia; el agente las lee sin
pasar por acá.

Dos cosas del archivo:

- **El vector se calcula al guardar**, no en un barrido diferido. HU-E9-04, primer criterio:
  una FAQ nueva queda «disponible para el agente» — si el vector llegara después, habría una
  ventana en la que la FAQ existe en la pantalla y no existe para quien pregunta.

  Cuando el proveedor de embeddings no contesta, la FAQ **se guarda igual** y queda marcada
  como obsoleta: perder la respuesta que alguien acaba de escribir porque un tercero está
  caído es peor que tenerla sin indexar hasta el próximo barrido.

- **`EliminarFAQ` existe y es la única baja real del sistema.** RN-03 pide que deje de estar
  disponible «de forma inmediata», y una FAQ no es un registro del negocio: no hay nada que
  auditar en una pregunta que ya no se hace.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from cheatsheet.contexts.conversational.application.errors import FAQInexistente
from cheatsheet.contexts.conversational.application.ports import (
    PortEmbeddings,
    PortRepositorioFAQ,
    PortUsosDeFAQ,
)
from cheatsheet.contexts.conversational.domain.faq import FAQ
from cheatsheet.contexts.conversational.domain.uso_de_faq import (
    SIN_USOS,
    ConteoDeUsos,
    Lapso,
    MotivoSinComparacion,
    Participacion,
    ventana_de_comparacion,
)
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.roles import RolUsuario
from cheatsheet.shared.zona_horaria import MesCalendario

logger = obtener_logger(__name__)

MOTIVO_SOLO_ADMIN = "Solo un Administrador puede administrar las respuestas frecuentes"


def _exigir_administrador(rol: RolUsuario) -> None:
    if rol is not RolUsuario.ADMINISTRADOR:
        raise EntradaInvalida(MOTIVO_SOLO_ADMIN)


@dataclass(frozen=True, slots=True)
class FAQConUsos:
    """Una FAQ con lo que se usó: el modelo de lectura de PAN-WA-02."""

    faq: FAQ
    conteo: ConteoDeUsos

    @property
    def usos_total(self) -> int:
        return self.conteo.total(self.faq.usos_anteriores)


@dataclass(frozen=True, slots=True)
class Comparacion:
    """La participación de la FAQ en los `dias` anteriores y posteriores a su última edición."""

    dias: int
    antes: Participacion
    despues: Participacion


@dataclass(frozen=True, slots=True)
class DetalleDeUso:
    """El detalle de una FAQ: o la comparación, o el motivo por el que no se puede hacer."""

    faq: FAQ
    conteo: ConteoDeUsos
    comparacion: Comparacion | None
    motivo: MotivoSinComparacion | None

    @property
    def usos_total(self) -> int:
        return self.conteo.total(self.faq.usos_anteriores)


class ListarFAQs:
    """PAN-WA-02. Todos los roles leen: el contador de usos es información del negocio."""

    def __init__(self, faqs: PortRepositorioFAQ, usos: PortUsosDeFAQ) -> None:
        self._faqs = faqs
        self._usos = usos

    async def ejecutar(self, *, ahora: datetime) -> list[FAQConUsos]:
        """Ordenadas por «Este mes», después por total, después por antigüedad."""
        conteos = await self._usos.conteos(MesCalendario.del_instante(ahora))
        vistas = [
            FAQConUsos(faq=faq, conteo=conteos.get(faq.id, SIN_USOS))
            for faq in await self._faqs.listar()
        ]
        return sorted(
            vistas,
            key=lambda v: (-v.conteo.este_mes, -v.usos_total, v.faq.created_at or ahora),
        )


class VerUsoDeFAQ:
    """El detalle de una FAQ: sus conteos y su participación antes y después de editarse.

    **Participación** = usos de la FAQ ÷ todas las respuestas con FAQ de la empresa en el mismo
    lapso (las de FAQ ya borradas incluidas: ADR-0012, punto 7).
    """

    def __init__(self, faqs: PortRepositorioFAQ, usos: PortUsosDeFAQ) -> None:
        self._faqs = faqs
        self._usos = usos

    async def ejecutar(self, *, faq_id: UUID, ahora: datetime) -> DetalleDeUso:
        faq = await _buscar(self._faqs, faq_id)
        conteo = (await self._usos.conteos(MesCalendario.del_instante(ahora))).get(faq.id, SIN_USOS)
        ventana = ventana_de_comparacion(
            editada_en=faq.editada_en,
            seguimiento_desde=faq.seguimiento_desde or faq.created_at or ahora,
            ahora=ahora,
        )
        if isinstance(ventana, MotivoSinComparacion):
            return DetalleDeUso(faq, conteo, comparacion=None, motivo=ventana)
        comparacion = Comparacion(
            dias=ventana.dias,
            antes=await self._participacion(faq.id, ventana.antes),
            despues=await self._participacion(faq.id, ventana.despues),
        )
        return DetalleDeUso(faq, conteo, comparacion=comparacion, motivo=None)

    async def _participacion(self, faq_id: UUID, lapso: Lapso) -> Participacion:
        return Participacion(
            usos=await self._usos.contar(desde=lapso.desde, hasta=lapso.hasta, faq_id=faq_id),
            total=await self._usos.contar(desde=lapso.desde, hasta=lapso.hasta, faq_id=None),
        )


class CrearFAQ:
    """HU-E9-04, primer criterio: aparece con contador en cero y disponible para el agente."""

    def __init__(
        self,
        faqs: PortRepositorioFAQ,
        embeddings: PortEmbeddings,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._faqs = faqs
        self._embeddings = embeddings
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        pregunta: str,
        respuesta: str,
        ahora: datetime,
        categoria_id: UUID | None = None,
    ) -> FAQ:
        _exigir_administrador(rol)
        # La validación de campos obligatorios la hace el agregado, con la frase de la
        # historia. No se repite acá: dos lugares que validan lo mismo son dos lugares que
        # pueden dejar de estar de acuerdo.
        faq = FAQ(
            id=uuid4(),
            empresa_id=empresa_id,
            pregunta=pregunta.strip(),
            respuesta=respuesta.strip(),
            categoria_id=categoria_id,
            created_at=ahora,
            updated_at=ahora,
            seguimiento_desde=ahora,
        )
        await self._faqs.agregar(faq)
        await indexar(self._faqs, self._embeddings, faq, ahora)
        await _auditar(self._publicador, empresa_id, usuario_id, faq, "crear_faq", ahora)
        return faq


class EditarFAQ:
    """Cambia el texto. Reindexar sólo si cambió la pregunta — el vector se calcula sobre ella."""

    def __init__(
        self,
        faqs: PortRepositorioFAQ,
        embeddings: PortEmbeddings,
        publicador: PublicadorDeEventos,
        usos: PortUsosDeFAQ,
    ) -> None:
        self._faqs = faqs
        self._usos = usos
        self._embeddings = embeddings
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        faq_id: UUID,
        pregunta: str,
        respuesta: str,
        ahora: datetime,
    ) -> FAQConUsos:
        _exigir_administrador(rol)
        faq = await _buscar(self._faqs, faq_id)
        faq.editar(pregunta=pregunta, respuesta=respuesta, momento=ahora)
        await self._faqs.guardar(faq)
        if faq.embedding_obsoleto:
            await indexar(self._faqs, self._embeddings, faq, ahora)
        await _auditar(self._publicador, empresa_id, usuario_id, faq, "editar_faq", ahora)
        conteos = await self._usos.conteos(MesCalendario.del_instante(ahora))
        return FAQConUsos(faq=faq, conteo=conteos.get(faq.id, SIN_USOS))


class EliminarFAQ:
    """HU-E9-04 RN-03: el agente deja de usarla **de inmediato**.

    La confirmación la pide la pantalla (cuarto criterio); acá se ejecuta. Es la única baja
    real del sistema — ver el docstring del módulo.
    """

    def __init__(self, faqs: PortRepositorioFAQ, publicador: PublicadorDeEventos) -> None:
        self._faqs = faqs
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        faq_id: UUID,
        ahora: datetime,
    ) -> None:
        _exigir_administrador(rol)
        faq = await _buscar(self._faqs, faq_id)
        await self._faqs.eliminar(faq_id)
        await _auditar(self._publicador, empresa_id, usuario_id, faq, "eliminar_faq", ahora)


class ReindexarFAQs:
    """El barrido que recalcula los vectores marcados obsoletos.

    Existe por dos motivos, y los dos están en el DER: recuperar las FAQ que se guardaron
    mientras el proveedor de embeddings estaba caído, y migrar de modelo sin recalcular todo de
    golpe. Mientras tanto lo obsoleto **se sigue sirviendo con su vector viejo**, que es mucho
    mejor que no responder nada.
    """

    def __init__(self, faqs: PortRepositorioFAQ, embeddings: PortEmbeddings) -> None:
        self._faqs = faqs
        self._embeddings = embeddings

    async def ejecutar(self, *, ahora: datetime) -> int:
        indexadas = 0
        for faq in await self._faqs.pendientes_de_indexar():
            if await indexar(self._faqs, self._embeddings, faq, ahora):
                indexadas += 1
        return indexadas


async def indexar(
    faqs: PortRepositorioFAQ, embeddings: PortEmbeddings, faq: FAQ, ahora: datetime
) -> bool:
    """Calcula y guarda el vector de una FAQ. **No hace fallar nada si el proveedor no está.**

    Devuelve si pudo. Cuando no, la FAQ queda con `embedding_obsoleto=True` y el barrido la
    alcanza — perder la respuesta que alguien acaba de escribir porque un tercero está caído
    es peor que tenerla sin indexar por un rato.

    Función y no método porque la usan tres casos de uso, y la alternativa era que dos de
    ellos llamaran al privado del tercero.
    """
    try:
        vector = await embeddings.vectorizar(faq.pregunta)
    except Exception:  # noqa: BLE001 — cualquier fallo del proveedor deja la FAQ sin indexar
        logger.warning("faq_sin_indexar", faq_id=str(faq.id))
        return False
    faq.marcar_indexada(embeddings.version, ahora)
    await faqs.guardar_vector(faq, vector)
    return True


async def _buscar(faqs: PortRepositorioFAQ, faq_id: UUID) -> FAQ:
    faq = await faqs.buscar_por_id(faq_id)
    if faq is None:
        raise FAQInexistente("La respuesta frecuente no existe")
    return faq


async def _auditar(
    publicador: PublicadorDeEventos,
    empresa_id: EmpresaId,
    usuario_id: UsuarioId,
    faq: FAQ,
    accion: str,
    ahora: datetime,
) -> None:
    await publicador.publicar(
        EventoAuditable(
            evento_id=uuid4(),
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            ocurrido_en=ahora,
            modulo=Modulo.CONVERSATIONAL,
            accion=accion,
            entidad_afectada=f"FAQ:{faq.id}",
            resultado=Resultado.COMPLETADO,
        )
    )


__all__ = [
    "Comparacion",
    "CrearFAQ",
    "DetalleDeUso",
    "EditarFAQ",
    "EliminarFAQ",
    "FAQConUsos",
    "ListarFAQs",
    "ReindexarFAQs",
    "VerUsoDeFAQ",
    "indexar",
]
