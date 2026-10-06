"""ACL sobre `identity`: a quién le corresponde una notificación (HU-E11-03 RN-02).

**De sólo lectura, y devuelve ids.** Este contexto no tiene nada que hacer con un email, un
nombre o un rol; lo único que necesita saber es a quién escribirle. Devolver usuarios enteros
sería darle a la bandeja de notificaciones acceso al padrón de personas de la empresa.

Lo que se importa de `identity` es su **puerto** —`PortRepositorioUsuario`, de la capa de
aplicación— y nunca su `domain/` ni su `infrastructure/` (regla R3). Lo que ese puerto devuelve
se lee por atributo, sin nombrar sus tipos: `activo`, `id` y `pref_suscripciones`, y de esta
última sólo el par (categoría, canal) comparado **por valor**. Es el mismo patrón que
`SaldoViaBilling` del épico 6.
"""

from __future__ import annotations

from cheatsheet.contexts.identity.application.ports import PortRepositorioUsuario
from cheatsheet.shared.empresa import EmpresaId, UsuarioId

#: El canal que alimenta el centro de notificaciones del panel.
#:
#: Fijo y no configurable acá: quien además quiera el aviso por mail lo recibe por el camino
#: del épico 2, que es otro adaptador y otro canal. Esta clase contesta una sola pregunta.
CANAL_DEL_PANEL = "PANEL"


class DestinatariosViaIdentity:
    """`PortDestinatarios`, respaldado por el repositorio publicado de `identity`."""

    def __init__(self, usuarios: PortRepositorioUsuario, *, empresa_id: EmpresaId) -> None:
        self._usuarios = usuarios
        self._empresa_id = empresa_id

    async def suscriptos_a(self, categoria: str) -> list[UsuarioId]:
        """Quiénes eligieron recibir esa categoría en el panel, y siguen activos.

        **Activos**: un usuario desactivado no entra al panel, así que una notificación suya
        es una fila que nadie va a leer nunca — y que además sigue contando en el globito de
        no leídas de una cuenta que ya no se usa.
        """
        elegidos: list[UsuarioId] = []
        for usuario in await self._usuarios.listar_de_empresa(self._empresa_id):
            if not usuario.activo:
                continue
            suscripciones = usuario.pref_suscripciones.suscripciones
            if any(
                # Comparado por valor y no por identidad de enum: nombrar los tipos de
                # `identity` sería importarlos, que es exactamente lo que R3 prohíbe.
                una.value == categoria and canal.value == CANAL_DEL_PANEL
                for una, canal in suscripciones
            ):
                elegidos.append(usuario.id)
        return elegidos


__all__ = ["CANAL_DEL_PANEL", "DestinatariosViaIdentity"]
