"""Mandar una plantilla de WhatsApp a revisión de Meta (U6, HU-E11-02 RN-03/RN-04).

Dos casos de uso del administrador y una pieza compartida con la conciliación:

- `EditarPlantilla`: cambia el cuerpo y, si es de WhatsApp, **lo manda a Meta antes de guardarlo**.
- `EnviarPlantillaAMeta`: el «Enviar a revisión» de la pantalla, sin tocar el texto.
- `enviar_a_meta`: crea o edita en Meta y aplica la respuesta sobre el agregado.

**Por qué Meta se llama dentro del caso de uso y no «después».** La respuesta de Meta decide si la
edición existe. Guardar primero y llamar después dejaría guardado un texto que Meta refutó (o que no
pudo recibir por el límite de 24 h), y la pantalla mostraría como vigente un cuerpo que no es el que
Meta tiene. Si Meta refuta o no responde, **no se guarda nada**: el error sale y la unidad de trabajo
se revierte. Este módulo no importa `conversational`: recibe `PortRevisionDeMeta`.

La única falla que sí se guarda es `MetaNoConectada`: no hay a quién mandársela, así que el texto
queda y la plantilla pasa a `SIN_ENVIAR` con el detalle a la vista; la conciliación la manda cuando
la empresa conecte WhatsApp.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from cheatsheet.contexts.business_config.application.errors import (
    MetaNoConectada,
    MetaRechazoLaPlantilla,
)
from cheatsheet.contexts.business_config.application.plantillas import exigir_administrador
from cheatsheet.contexts.business_config.application.ports import (
    PortRepositorioPlantillas,
    PortRevisionDeMeta,
    RespuestaDeMeta,
)
from cheatsheet.contexts.business_config.domain.estados_de_meta import estado_desde_nodo
from cheatsheet.contexts.business_config.domain.plantilla import (
    PATRON_DE_VARIABLE,
    EstadoDeAprobacion,
    PlantillaDeNotificacion,
    ejemplos_de,
)
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.roles import RolUsuario

DETALLE_SIN_CONECTAR = "WhatsApp no está conectado"

#: Estados desde los que «Enviar a revisión» tiene sentido: nunca aceptada, o rechazada.
REENVIABLES = frozenset({EstadoDeAprobacion.SIN_ENVIAR, EstadoDeAprobacion.RECHAZADA})


def ejemplos_del_cuerpo(plantilla: PlantillaDeNotificacion) -> dict[str, str]:
    """Un ejemplo por variable **que el cuerpo usa**, en el orden en que aparecen.

    Meta exige la cantidad exacta de parámetros (error 132000): ni una de más ni una de menos.
    """
    todos = ejemplos_de(plantilla.codigo)
    usadas = dict.fromkeys(PATRON_DE_VARIABLE.findall(plantilla.cuerpo))
    return {variable: todos[variable] for variable in usadas if variable in todos}


async def enviar_a_meta(
    plantilla: PlantillaDeNotificacion, revision: PortRevisionDeMeta, ahora: datetime
) -> None:
    """Crea la plantilla en Meta, o edita la que ya existe, y aplica lo que Meta contestó.

    Crea si nunca se aceptó (no hay id) o si Meta la deshabilitó; edita si no. Levanta
    `MetaRechazoLaPlantilla`, `MetaNoDisponible` o `MetaNoConectada` **sin tocar el repositorio**:
    quien llama decide qué se guarda.
    """
    ejemplos = ejemplos_del_cuerpo(plantilla)
    if plantilla.meta_plantilla_id is None or (
        plantilla.estado_aprobacion is EstadoDeAprobacion.DESHABILITADA
    ):
        respuesta, nombre = await _crear(plantilla, revision, ejemplos)
    else:
        respuesta = await revision.editar(
            meta_plantilla_id=plantilla.meta_plantilla_id,
            cuerpo=plantilla.cuerpo,
            ejemplos=ejemplos,
        )
        nombre = plantilla.nombre_en_meta or plantilla.codigo
    plantilla.registrar_envio_a_meta(
        meta_plantilla_id=respuesta.meta_plantilla_id, nombre_en_meta=nombre, momento=ahora
    )
    plantilla.aplicar_respuesta_de_meta(
        estado_desde_nodo(respuesta.estado) or EstadoDeAprobacion.PENDIENTE,
        motivo=None,
        detalle=None,
        momento=ahora,
        categoria=respuesta.categoria,
    )


async def _crear(
    plantilla: PlantillaDeNotificacion, revision: PortRevisionDeMeta, ejemplos: dict[str, str]
) -> tuple[RespuestaDeMeta, str]:
    nombre = plantilla.nombre_para_crear()
    try:
        return await _crear_con(plantilla, revision, nombre, ejemplos), nombre
    except MetaRechazoLaPlantilla as exc:
        if not exc.nombre_en_uso:
            raise
    # «Nombre en uso» (la WABA ya tiene una a mano con ese nombre e idioma): se prueba el
    # siguiente sufijo, una sola vez por intento.
    otro = plantilla.siguiente_nombre(nombre)
    return await _crear_con(plantilla, revision, otro, ejemplos), otro


async def _crear_con(
    plantilla: PlantillaDeNotificacion,
    revision: PortRevisionDeMeta,
    nombre: str,
    ejemplos: dict[str, str],
) -> RespuestaDeMeta:
    return await revision.crear(
        nombre=nombre, idioma=plantilla.idioma, cuerpo=plantilla.cuerpo, ejemplos=ejemplos
    )


async def _mandar_y_guardar(
    plantilla: PlantillaDeNotificacion,
    plantillas: PortRepositorioPlantillas,
    revision: PortRevisionDeMeta,
    ahora: datetime,
) -> None:
    if plantilla.es_de_whatsapp:
        try:
            await enviar_a_meta(plantilla, revision, ahora)
        except MetaNoConectada:
            plantilla.marcar_sin_enviar(DETALLE_SIN_CONECTAR, ahora)
    await plantillas.guardar(plantilla)


class EditarPlantilla:
    """HU-E11-02, segundo y tercer criterio, más lo que Meta pide de una plantilla.

    La validación de variables y del borde del texto la hace el agregado, con sus frases. No se
    repite acá: dos lugares que validan lo mismo son dos lugares que pueden dejar de estar de
    acuerdo.
    """

    def __init__(
        self,
        plantillas: PortRepositorioPlantillas,
        publicador: PublicadorDeEventos,
        revision: PortRevisionDeMeta,
    ) -> None:
        self._plantillas = plantillas
        self._publicador = publicador
        self._revision = revision

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        plantilla_id: UUID,
        cuerpo: str,
        ahora: datetime,
    ) -> PlantillaDeNotificacion:
        exigir_administrador(rol)
        plantilla = await self._plantillas.buscar_por_id(plantilla_id)
        if plantilla is None:
            raise EntradaInvalida("La plantilla no existe")
        plantilla.editar(cuerpo, ahora)
        await _mandar_y_guardar(plantilla, self._plantillas, self._revision, ahora)
        await _auditar(
            self._publicador, empresa_id, usuario_id, plantilla, "editar_plantilla", ahora
        )
        return plantilla


class EnviarPlantillaAMeta:
    """El «Enviar a revisión» de PAN-CFG-NOT: reenvía una `SIN_ENVIAR` o `RECHAZADA` tal como está."""

    def __init__(
        self,
        plantillas: PortRepositorioPlantillas,
        publicador: PublicadorDeEventos,
        revision: PortRevisionDeMeta,
    ) -> None:
        self._plantillas = plantillas
        self._publicador = publicador
        self._revision = revision

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        plantilla_id: UUID,
        ahora: datetime,
    ) -> PlantillaDeNotificacion:
        exigir_administrador(rol)
        plantilla = await self._plantillas.buscar_por_id(plantilla_id)
        if plantilla is None:
            raise EntradaInvalida("La plantilla no existe")
        if not plantilla.es_de_whatsapp or plantilla.estado_aprobacion not in REENVIABLES:
            raise EntradaInvalida("Esta plantilla no necesita reenviarse a Meta.")
        plantilla.exigir_enviable()
        await _mandar_y_guardar(plantilla, self._plantillas, self._revision, ahora)
        await _auditar(
            self._publicador, empresa_id, usuario_id, plantilla, "enviar_plantilla_a_meta", ahora
        )
        return plantilla


async def _auditar(
    publicador: PublicadorDeEventos,
    empresa_id: EmpresaId,
    usuario_id: UsuarioId,
    plantilla: PlantillaDeNotificacion,
    accion: str,
    ahora: datetime,
) -> None:
    await publicador.publicar(
        EventoAuditable(
            evento_id=uuid4(),
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            ocurrido_en=ahora,
            modulo=Modulo.BUSINESS_CONFIG,
            accion=accion,
            entidad_afectada=f"PlantillaDeNotificacion:{plantilla.id}",
            resultado=Resultado.COMPLETADO,
        )
    )


__all__ = [
    "DETALLE_SIN_CONECTAR",
    "EditarPlantilla",
    "EnviarPlantillaAMeta",
    "ejemplos_del_cuerpo",
    "enviar_a_meta",
]
