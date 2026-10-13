"""Un `CanalDeAvisos` de mentira para los tests de `AvisoPorWhatsApp` (U7, D-U7-4).

Registra lo que el adaptador le pidió que notificara y contesta lo que se le programe: un
resultado, o una excepción (un canal que explota). Sin red y sin base.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from cheatsheet.contexts.scheduling.infrastructure.avisos import EnvioParaAviso, ResultadoLocal


@dataclass(frozen=True)
class Notificacion:
    cliente_id: UUID
    telefono: str
    envio: EnvioParaAviso

    @property
    def texto(self) -> str:
        return self.envio.texto

    @property
    def nombre_de_plantilla(self) -> str | None:
        plantilla = self.envio.plantilla
        return plantilla.nombre if plantilla is not None else None


class CanalDeAvisosFalso:
    def __init__(
        self, *, falla: Exception | None = None, resultado: ResultadoLocal | None = None
    ) -> None:
        self.notificaciones: list[Notificacion] = []
        self._falla = falla
        self._resultado = resultado or ResultadoLocal(enviado=True)

    async def notificar(
        self, *, cliente_id: UUID, telefono: str, envio: EnvioParaAviso
    ) -> ResultadoLocal:
        if self._falla is not None:
            raise self._falla
        self.notificaciones.append(Notificacion(cliente_id, telefono, envio))
        return self._resultado

    @property
    def textos(self) -> list[tuple[str, str]]:
        """Lo que salió como texto de fábrica: `(teléfono, texto)`."""
        return [(n.telefono, n.texto) for n in self.notificaciones if n.envio.plantilla is None]

    @property
    def plantillas(self) -> list[tuple[str, str, str, dict[str, str]]]:
        """Lo que salió como plantilla: `(teléfono, nombre, idioma, parámetros)`."""
        return [
            (
                n.telefono,
                n.envio.plantilla.nombre,
                n.envio.plantilla.idioma,
                dict(n.envio.plantilla.parametros),
            )
            for n in self.notificaciones
            if n.envio.plantilla is not None
        ]
