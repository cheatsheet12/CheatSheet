"""La escena compartida de los tests de edición y de reenvío de plantillas a Meta (U6)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from cheatsheet.contexts.business_config.application.ports import RespuestaDeMeta
from cheatsheet.contexts.business_config.application.revision_de_meta import (
    EditarPlantilla,
    EnviarPlantillaAMeta,
)
from cheatsheet.contexts.business_config.domain.plantilla import (
    EstadoDeAprobacion,
    PlantillaDeNotificacion,
)
from cheatsheet.contexts.business_config.domain.regla import CanalNotificacion
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.roles import RolUsuario

from .dobles_plantillas import PublicadorFalso, RepositorioPlantillasEnMemoria, RevisionDeMetaFalsa

EMPRESA = EmpresaId(uuid4())
USUARIO = UsuarioId(uuid4())
AHORA = datetime(2026, 10, 15, 13, 0, tzinfo=UTC)
CUERPO_VIEJO = "Hola {{nombre}}, te recordamos tu turno el {{fecha}} a las {{hora}}."
CUERPO_NUEVO = "Hola {{nombre}}, te esperamos el {{fecha}} a las {{hora}} en {{recurso}}. Gracias."

APROBADA = RespuestaDeMeta(meta_plantilla_id="meta-9", estado="APPROVED", categoria="UTILITY")
PENDIENTE = RespuestaDeMeta(meta_plantilla_id="meta-9", estado="PENDING", categoria="UTILITY")


def una_plantilla(
    estado: EstadoDeAprobacion = EstadoDeAprobacion.SIN_ENVIAR,
    *,
    canal: CanalNotificacion = CanalNotificacion.WHATSAPP,
    cuerpo: str = CUERPO_VIEJO,
    **extra: object,
) -> PlantillaDeNotificacion:
    return PlantillaDeNotificacion(
        id=uuid4(),
        empresa_id=EMPRESA,
        codigo="turno_confirmado",
        canal=canal,
        idioma="es_AR",
        cuerpo=cuerpo,
        estado_aprobacion=estado,
        nombre_en_meta="turno_confirmado" if canal is CanalNotificacion.WHATSAPP else None,
        **extra,  # type: ignore[arg-type]
    )


class Escena:
    def __init__(
        self, plantilla: PlantillaDeNotificacion, revision: RevisionDeMetaFalsa | None = None
    ) -> None:
        self.plantilla = plantilla
        self.repositorio = RepositorioPlantillasEnMemoria(plantilla)
        self.revision = revision or RevisionDeMetaFalsa()
        self.publicador = PublicadorFalso()

    async def editar(
        self, cuerpo: str = CUERPO_NUEVO, rol: RolUsuario = RolUsuario.ADMINISTRADOR
    ) -> PlantillaDeNotificacion:
        return await EditarPlantilla(self.repositorio, self.publicador, self.revision).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=rol,
            plantilla_id=self.plantilla.id,
            cuerpo=cuerpo,
            ahora=AHORA,
        )

    async def enviar(self) -> PlantillaDeNotificacion:
        return await EnviarPlantillaAMeta(
            self.repositorio, self.publicador, self.revision
        ).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.ADMINISTRADOR,
            plantilla_id=self.plantilla.id,
            ahora=AHORA,
        )

    @property
    def guardada(self) -> PlantillaDeNotificacion:
        return self.repositorio.filas[self.plantilla.id]


__all__ = [
    "AHORA",
    "APROBADA",
    "CUERPO_NUEVO",
    "CUERPO_VIEJO",
    "EMPRESA",
    "PENDIENTE",
    "USUARIO",
    "Escena",
    "una_plantilla",
]
