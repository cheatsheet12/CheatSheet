"""La conciliación de las plantillas de una empresa con su cuenta de Meta (U6, D-U6-9).

**Es la columna vertebral de la sincronización.** El estado de una plantilla llega por webhook, pero
ese webhook depende de una configuración de la app que no admite override por cuenta: si no llega,
una plantilla quedaría `PENDIENTE` para siempre. Beat corre esto cada tanto, por empresa:

1. Lee de Meta **todas** las plantillas de la WABA. Si Meta no responde, no se toca nada (ni se
   siembra): la corrida siguiente lee lo mismo y recupera.
2. Siembra las siete de fábrica que falten (`ListarPlantillas`).
3. A cada plantilla de WhatsApp la busca en lo que Meta devolvió, por id y, si no, por nombre e
   idioma. Si la encuentra, aplica su estado, su motivo y detecta el texto divergente. Si no la
   encuentra y nunca se aceptó (`SIN_ENVIAR`), **la manda**: así una empresa que nunca entró a
   PAN-CFG-NOT también tiene sus plantillas en revisión. Que se la busque por nombre antes de
   crearla es lo que hace seguro un timeout al crear: la corrida siguiente la encuentra.

**Texto divergente (D-U6-5).** Si Meta aceptó una edición y la respuesta no llegó, la transacción se
revirtió y en Meta quedó un texto que no guardamos. Se compara el cuerpo y se deja un aviso: el
cuerpo local **no** se pisa con el de Meta, porque el texto lo decide el administrador.

**Una aprobada que Meta ya no lista (G3)** vuelve a `SIN_ENVIAR` con un aviso, solo si la
lectura fue entera (`estados_completos`): sin eso el envío fallaría con 132001. Una que Meta ya refutó (`SIN_ENVIAR` con el texto de Meta como detalle) no se reintenta en
cada corrida: queda a la espera de que el administrador la edite o la reenvíe.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from cheatsheet.contexts.business_config.application.errors import (
    MetaNoConectada,
    MetaNoDisponible,
    MetaRechazoLaPlantilla,
)
from cheatsheet.contexts.business_config.application.plantillas import ListarPlantillas
from cheatsheet.contexts.business_config.application.ports import (
    EstadoEnMeta,
    PortRepositorioPlantillas,
    PortRevisionDeMeta,
)
from cheatsheet.contexts.business_config.application.revision_de_meta import (
    DETALLE_SIN_CONECTAR,
    enviar_a_meta,
)
from cheatsheet.contexts.business_config.domain.estados_de_meta import estado_desde_nodo
from cheatsheet.contexts.business_config.domain.plantilla import (
    LARGO_MAXIMO_ID_EN_META,
    EstadoDeAprobacion,
    PlantillaDeNotificacion,
)
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida

logger = obtener_logger(__name__)

DETALLE_DIVERGENTE = "El texto en Meta no coincide con el guardado: volvé a guardar la plantilla."

DETALLE_YA_NO_ESTA_EN_META = "Meta ya no la tiene: volvé a enviarla a revisión."

SIN_ESTADO_QUE_LEER = frozenset({EstadoDeAprobacion.SIN_ENVIAR})


@dataclass(frozen=True, slots=True)
class ResumenDeConciliacion:
    """Qué hizo una corrida. `interrumpida` dice por qué no llegó al final, si no llegó."""

    sembradas: int = 0
    enviadas: int = 0
    actualizadas: int = 0
    divergentes: int = 0
    interrumpida: str | None = None


class ConciliarPlantillasConMeta:
    """Sin rol: la llama el barrido de Beat, una vez por empresa."""

    def __init__(self, plantillas: PortRepositorioPlantillas, revision: PortRevisionDeMeta) -> None:
        self._plantillas = plantillas
        self._revision = revision

    async def ejecutar(self, *, empresa_id: EmpresaId, ahora: datetime) -> ResumenDeConciliacion:
        try:
            en_meta = await self._revision.estados()
        except MetaNoDisponible:
            logger.warning("conciliacion_de_plantillas_meta_no_disponible")
            return ResumenDeConciliacion(interrumpida="meta_no_disponible")
        except MetaNoConectada:
            return ResumenDeConciliacion(interrumpida="no_conectada")

        antes = len(await self._plantillas.listar())
        plantillas = await ListarPlantillas(self._plantillas).ejecutar(
            empresa_id=empresa_id, ahora=ahora
        )
        en_meta = [una for una in en_meta if _id_cabe(una)]
        por_id = {una.meta_plantilla_id: una for una in en_meta}
        por_nombre = {(una.nombre, una.idioma): una for una in en_meta}

        enviadas = actualizadas = divergentes = 0
        interrumpida: str | None = None
        for plantilla in plantillas:
            if not plantilla.es_de_whatsapp:
                continue
            nombre = (plantilla.nombre_en_meta or plantilla.codigo, plantilla.idioma)
            encontrada = por_id.get(plantilla.meta_plantilla_id or "") or por_nombre.get(nombre)
            if encontrada is not None:
                cambio, diverge = self._aplicar(plantilla, encontrada, ahora)
                actualizadas += cambio
                divergentes += diverge
                if cambio:
                    await self._plantillas.guardar(plantilla)
            elif plantilla.estado_aprobacion is EstadoDeAprobacion.APROBADA:
                actualizadas += await self._retirar_aprobacion(plantilla, ahora)
            elif plantilla.estado_aprobacion is EstadoDeAprobacion.SIN_ENVIAR:
                try:
                    enviadas += await self._enviar(plantilla, ahora)
                except (MetaNoDisponible, MetaNoConectada) as exc:
                    interrumpida = (
                        "meta_no_disponible"
                        if isinstance(exc, MetaNoDisponible)
                        else "no_conectada"
                    )
                    break
        return ResumenDeConciliacion(
            sembradas=len(plantillas) - antes,
            enviadas=enviadas,
            actualizadas=actualizadas,
            divergentes=divergentes,
            interrumpida=interrumpida,
        )

    async def _retirar_aprobacion(self, plantilla: PlantillaDeNotificacion, ahora: datetime) -> int:
        """G3: una aprobada que Meta ya no lista deja de serlo. 1 si cambió.

        Seguir «aprobada» haría que el envío saliera como plantilla inexistente (Meta 132001) sin
        texto de respaldo. Pasa a `SIN_ENVIAR`, el mismo estado al que lleva un `DELETED` de Meta:
        `ConsultarPlantillaParaEnviar` ya no la devuelve y el adaptador manda su texto. **No se
        reenvía sola**: tiene un detalle, como una refutada, y la decisión de volver a mandarla es
        del administrador (puede que Meta la haya borrado a propósito).

        Solo con una lista exhaustiva: `estados()` o la trae entera o falla, y el doble de
        desarrollo, que no recuerda nada, lo avisa con `estados_completos`.
        """
        if not self._revision.estados_completos:
            return 0
        cambio = plantilla.aplicar_respuesta_de_meta(
            EstadoDeAprobacion.SIN_ENVIAR,
            motivo=None,
            detalle=DETALLE_YA_NO_ESTA_EN_META,
            momento=ahora,
        )
        if cambio:
            logger.warning("plantilla_aprobada_que_meta_ya_no_lista", codigo=plantilla.codigo)
            await self._plantillas.guardar(plantilla)
        return int(cambio)

    async def _enviar(self, plantilla: PlantillaDeNotificacion, ahora: datetime) -> int:
        """1 si la mandó. Una ya refutada, o con un texto que Meta no acepta, espera al administrador."""
        if plantilla.detalle_meta not in (None, DETALLE_SIN_CONECTAR):
            return 0
        try:
            plantilla.exigir_enviable()
        except EntradaInvalida:
            logger.warning("plantilla_con_texto_no_enviable", codigo=plantilla.codigo)
            return 0
        try:
            await enviar_a_meta(plantilla, self._revision, ahora)
        except MetaRechazoLaPlantilla as exc:
            # Meta la refutó: queda a la vista con su texto, sin reintentar en cada corrida.
            plantilla.marcar_sin_enviar(str(exc), ahora)
            await self._plantillas.guardar(plantilla)
            return 0
        await self._plantillas.guardar(plantilla)
        return 1

    def _aplicar(
        self, plantilla: PlantillaDeNotificacion, en_meta: EstadoEnMeta, ahora: datetime
    ) -> tuple[bool, bool]:
        """(cambió algo, el texto diverge). Aplica el estado que Meta informa."""
        estado = estado_desde_nodo(en_meta.estado)
        if estado is None:
            logger.warning("plantilla_estado_meta_desconocido", estado=en_meta.estado)
            return False, False
        vinculada = plantilla.meta_plantilla_id != en_meta.meta_plantilla_id
        if vinculada:
            plantilla.vincular_con_meta(en_meta.meta_plantilla_id)
        diverge = (
            estado not in SIN_ESTADO_QUE_LEER
            and en_meta.cuerpo is not None
            and en_meta.cuerpo != plantilla.cuerpo
        )
        mismo_estado = estado is plantilla.estado_aprobacion
        motivo = en_meta.motivo or (plantilla.motivo_meta if mismo_estado else None)
        cambio = plantilla.aplicar_respuesta_de_meta(
            estado,
            motivo=motivo,
            detalle=_detalle(plantilla, mismo_estado, motivo, diverge),
            momento=ahora,
            categoria=en_meta.categoria,
        )
        return cambio or vinculada, diverge


def _id_cabe(en_meta: EstadoEnMeta) -> bool:
    """Un id de Meta más largo que su columna no se guarda ni se corta: se ignora y se avisa."""
    if len(en_meta.meta_plantilla_id) <= LARGO_MAXIMO_ID_EN_META:
        return True
    logger.warning("plantilla_meta_id_demasiado_largo", largo=len(en_meta.meta_plantilla_id))
    return False


def _detalle(
    plantilla: PlantillaDeNotificacion, mismo_estado: bool, motivo: str | None, diverge: bool
) -> str | None:
    """El detalle que queda: el aviso de divergencia, o el que ya había si nada cambió."""
    if diverge:
        return DETALLE_DIVERGENTE
    if plantilla.detalle_meta == DETALLE_DIVERGENTE:
        return None
    if mismo_estado and motivo == plantilla.motivo_meta:
        return plantilla.detalle_meta
    return None


__all__ = [
    "DETALLE_DIVERGENTE",
    "DETALLE_YA_NO_ESTA_EN_META",
    "ConciliarPlantillasConMeta",
    "ResumenDeConciliacion",
]
