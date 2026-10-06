"""Donde `scheduling` recibe su acceso a `master_data` y a su canal de avisos.

La misma forma que `mercadopago.py`, `padron.py` y `arca.py`, y por la misma razón: acá se
encuentran contextos, y la infraestructura de uno no puede meter mano en la de otro (R3). El
ensamblado ocurre en el composition root, por encima de todos.

Tres piezas se arman acá:

- **El catálogo de servicios agendables**, que sale de `master_data` (HU-E7-04 RN-02).
- **El directorio de clientes**, que sale del mismo contexto y contesta a qué número escribir
  (HU-E7-02 RN-03).
- **El avisador**, que manda por el canal de WhatsApp de la empresa. El canal se arma en
  `api/mensajeria.py` (ADR-0011 §2) y llega ya armado.

Se construyen **por request** y no cacheadas por proceso: las tres están atadas a la
transacción y a la empresa del pedido. Es la misma conclusión de `mercadopago.py`.
"""

from __future__ import annotations

from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.contexts.master_data.infrastructure.repositories import (
    RepositorioClientePostgres,
    RepositorioServicioPostgres,
)
from cheatsheet.contexts.scheduling.application.ports import (
    PortCatalogoDeServicios,
    PortDirectorioDeClientes,
    PortNotificadorDeTurnos,
)
from cheatsheet.contexts.scheduling.application.turnos import Avisador
from cheatsheet.contexts.scheduling.infrastructure.avisos import AvisoPorWhatsApp, CanalDeTexto
from cheatsheet.contexts.scheduling.infrastructure.catalogo import (
    CatalogoViaMasterData,
    ClientesViaMasterData,
)
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.roles import RolUsuario


def armar_catalogo(
    unidad: UnidadDeTrabajo, *, empresa_id: EmpresaId, rol: RolUsuario
) -> PortCatalogoDeServicios:
    """El catálogo de servicios agendables de esta empresa, en esta transacción.

    El rol viaja porque el ACL actúa **en nombre de quien hizo el pedido**: usar una identidad
    de servicio saltearía el control de lectura de `master_data`, que es justamente el tipo de
    atajo que después nadie recuerda haber tomado.
    """
    return CatalogoViaMasterData(
        RepositorioServicioPostgres(unidad.sesion), empresa_id=empresa_id, rol=rol
    )


def armar_directorio(unidad: UnidadDeTrabajo, *, empresa_id: EmpresaId) -> PortDirectorioDeClientes:
    return ClientesViaMasterData(RepositorioClientePostgres(unidad.sesion), empresa_id=empresa_id)


def armar_notificador(canal: CanalDeTexto) -> PortNotificadorDeTurnos:
    """Por dónde sale el aviso de un turno: WhatsApp, por el canal que el llamador ya armó.

    **El canal llega armado** (ADR-0011 §2): `api/mensajeria.armar_mensajeria` lo arma una vez por
    unidad de trabajo y este módulo no depende de `conversational`. El agente **no** usa esto: arma
    su propio `Avisador` con un notificador silencioso (`api/conversacional.py`), porque confirma
    en la conversación.
    """
    return AvisoPorWhatsApp(canal)


def armar_avisador(
    unidad: UnidadDeTrabajo,
    *,
    empresa_id: EmpresaId,
    rol: RolUsuario,
    canal: CanalDeTexto,
) -> Avisador:
    """Las tres piezas del aviso, atadas: cliente, servicio y canal."""
    return Avisador(
        clientes=armar_directorio(unidad, empresa_id=empresa_id),
        servicios=armar_catalogo(unidad, empresa_id=empresa_id, rol=rol),
        notificador=armar_notificador(canal),
    )


__all__ = ["armar_avisador", "armar_catalogo", "armar_directorio", "armar_notificador"]
