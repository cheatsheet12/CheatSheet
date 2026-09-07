"""Donde `reporting` recibe su acceso a los otros cuatro contextos.

La misma forma que `agenda.py`, `mercadopago.py`, `padron.py`, `arca.py` y `conversacional.py`,
y por la misma razón: acá se encuentran contextos, y la infraestructura de uno no puede meter
mano en la de otro (R3). El ensamblado ocurre en el composition root, por encima de todos.

Este es el que más contextos junta de todo el sistema —cuatro— y por eso conviene decir en voz
alta qué **no** puede hacer con ellos: los cuatro ACL que arma son de sólo lectura. Ninguno
tiene un método que emita, cobre, reserve o cancele. Un bug en la reportería no puede tocar un
comprobante, y eso no depende de que nadie lo llame: depende de que no exista la llamada.

Se construyen **por request**, no cacheados por proceso: los cuatro están atados a la
transacción y a la empresa del pedido. Es la misma conclusión de los cinco anteriores.
"""

from __future__ import annotations

from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.contexts.billing.infrastructure.repositorio_comprobante import (
    RepositorioComprobantePostgres,
)
from cheatsheet.contexts.identity.application.empresa import ConsultarDatosFiscales
from cheatsheet.contexts.identity.infrastructure.repositories import RepositorioEmpresaPostgres
from cheatsheet.contexts.observability.infrastructure.repository import (
    RepositorioDeAuditoriaPostgres,
)
from cheatsheet.contexts.payments.infrastructure.repositories import RepositorioCobroPostgres
from cheatsheet.contexts.reporting.application.ports import (
    PortAgendaLeida,
    PortAvisoAlContador,
    PortBitacora,
    PortCobranzas,
    PortFacturacion,
)
from cheatsheet.contexts.reporting.infrastructure.acl import (
    AgendaViaSchedulingLeida,
    BitacoraViaObservability,
    CobranzasViaPayments,
    FacturacionViaBilling,
)
from cheatsheet.contexts.reporting.infrastructure.avisos import crear_aviso_al_contador
from cheatsheet.contexts.scheduling.infrastructure.repositories import RepositorioTurnoPostgres
from cheatsheet.platform.email import crear_transporte
from cheatsheet.platform.settings import Settings
from cheatsheet.shared.empresa import EmpresaId

#: Cómo se nombra a la empresa en el mail del contador cuando todavía no completó el alta.
#:
#: Un rótulo y no una cadena vacía: el asunto del correo dice «X te compartió su paquete
#: contable», y sin nombre esa frase queda coja justo en el mensaje que tiene que dar confianza.
NOMBRE_PROVISORIO = "Tu cliente"


def armar_facturacion(unidad: UnidadDeTrabajo) -> PortFacturacion:
    """Lo emitido, leído por el repositorio publicado de `billing`."""
    return FacturacionViaBilling(RepositorioComprobantePostgres(unidad.sesion))


def armar_cobranzas(unidad: UnidadDeTrabajo) -> PortCobranzas:
    return CobranzasViaPayments(RepositorioCobroPostgres(unidad.sesion))


def armar_agenda_leida(unidad: UnidadDeTrabajo) -> PortAgendaLeida:
    return AgendaViaSchedulingLeida(RepositorioTurnoPostgres(unidad.sesion))


def armar_bitacora(unidad: UnidadDeTrabajo) -> PortBitacora:
    """La bitácora, por el mismo repositorio que la escribe.

    El que escribe y el que lee son el mismo adaptador porque son la misma tabla; lo que separa
    a este consumidor del otro es el **puerto**: `PortBitacora` no tiene `agregar`.
    """
    return BitacoraViaObservability(RepositorioDeAuditoriaPostgres(unidad.sesion))


async def armar_nombre_de_empresa(unidad: UnidadDeTrabajo, empresa_id: EmpresaId) -> str:
    """Cómo se llama la empresa, para el correo del contador.

    Sale del servicio de aplicación publicado de `identity` —el mismo que `billing` usa para
    saber la condición IVA del emisor— y no de su repositorio: un consumidor recibe la
    respuesta a su pregunta, no la fila (ADR-0003).
    """
    datos = await ConsultarDatosFiscales(RepositorioEmpresaPostgres(unidad.sesion)).ejecutar(
        empresa_id=empresa_id
    )
    return datos.razon_social or NOMBRE_PROVISORIO


def armar_aviso_al_contador(settings: Settings) -> PortAvisoAlContador:
    """Por dónde sale el mail con el enlace. El mismo transporte que las invitaciones."""
    return crear_aviso_al_contador(settings, crear_transporte(settings))


__all__ = [
    "NOMBRE_PROVISORIO",
    "armar_agenda_leida",
    "armar_aviso_al_contador",
    "armar_bitacora",
    "armar_cobranzas",
    "armar_facturacion",
    "armar_nombre_de_empresa",
]
