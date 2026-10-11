"""Los dobles de los colaboradores de `conversational`: canal, directorio y publicador."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID, uuid4

from cheatsheet.shared.auditoria import EventoAuditable


class MensajeriaEnMemoria:
    """Guarda lo que se mandó. `caida=True` simula un canal que no acepta nada."""

    def __init__(self, *, caida: bool = False) -> None:
        self.enviados: list[tuple[str, str]] = []
        self.caida = caida

    async def enviar(self, *, telefono: str, texto: str) -> str:
        if self.caida:
            raise RuntimeError("WhatsApp no responde")
        self.enviados.append((telefono, texto))
        return f"wamid-{len(self.enviados)}"

    async def enviar_plantilla(
        self, *, telefono: str, nombre: str, idioma: str, parametros: Mapping[str, str]
    ) -> str:
        del telefono, nombre, idioma, parametros
        raise AssertionError("el agente y el operador contestan con texto, nunca con plantilla")

    @property
    def textos(self) -> list[str]:
        return [texto for _, texto in self.enviados]


class DirectorioEnMemoria:
    def __init__(self, conocidos: dict[str, tuple[UUID, str]] | None = None) -> None:
        self.conocidos = conocidos or {}
        self.altas: list[str] = []

    async def cliente_de(self, telefono: str) -> tuple[UUID, str] | None:
        return self.conocidos.get(telefono)

    async def telefono_de(self, cliente_id: UUID) -> str | None:
        return next(
            (telefono for telefono, (uno, _) in self.conocidos.items() if uno == cliente_id),
            None,
        )

    async def alta_rapida(self, *, telefono: str, nombre: str) -> UUID:
        self.altas.append(telefono)
        nuevo = uuid4()
        self.conocidos[telefono] = (nuevo, nombre)
        return nuevo


class PublicadorEnMemoria:
    def __init__(self) -> None:
        self.eventos: list[object] = []

    async def publicar(self, evento: object) -> None:
        self.eventos.append(evento)

    def de_la_accion(self, accion: str) -> list[EventoAuditable]:
        """Los eventos auditables de esa acción, con su forma tipada."""
        return [
            uno for uno in self.eventos if isinstance(uno, EventoAuditable) and uno.accion == accion
        ]

    @property
    def acciones(self) -> list[str]:
        return [getattr(uno, "accion", "") for uno in self.eventos]

    @property
    def iniciadores(self) -> list[str]:
        """Qué iniciador quedó en cada evento. **HS-T2 RN-05** se afirma con esto."""
        return [str(getattr(uno, "quien_inicio", "")) for uno in self.eventos]


__all__ = ["DirectorioEnMemoria", "MensajeriaEnMemoria", "PublicadorEnMemoria"]
