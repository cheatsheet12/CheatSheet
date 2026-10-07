"""Cableado de `payments` sobre una unidad de trabajo.

Solo los repositorios. **La pasarela y los dos ACL cruzados no se arman aca**: resolver el
token de MercadoPago pasa por `integrations`, el saldo por `billing` y la cadena por
`business_config`, y la infraestructura de un contexto no puede meter mano en la de otro (R3).
Se arman en `api/mercadopago.py`, el composition root, que es la unica capa que puede cablear
dos contextos — el mismo lugar donde `api/arca.py` arma los clientes de WSFEv1.
"""

from __future__ import annotations

from dataclasses import dataclass

from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.contexts.payments.application.ports import (
    PortRepositorioCobro,
    PortRepositorioRecordatorios,
    PortRepositorioReembolso,
)
from cheatsheet.contexts.payments.application.ports_envio import PortAislamiento
from cheatsheet.contexts.payments.infrastructure.aislamiento import AislamientoConSavepoint
from cheatsheet.contexts.payments.infrastructure.repositories import RepositorioCobroPostgres
from cheatsheet.contexts.payments.infrastructure.repositorio_recordatorio import (
    RepositorioRecordatoriosPostgres,
)
from cheatsheet.contexts.payments.infrastructure.repositorio_reembolso import (
    RepositorioReembolsoPostgres,
)


@dataclass(frozen=True, slots=True)
class Cobros:
    """Las piezas que necesita un request, atadas a una transaccion."""

    cobros: PortRepositorioCobro
    recordatorios: PortRepositorioRecordatorios
    reembolsos: PortRepositorioReembolso
    #: El savepoint por cobro del barrido de recordatorios (U5, H1).
    aislamiento: PortAislamiento

    @classmethod
    def armar(cls, unidad: UnidadDeTrabajo) -> Cobros:
        return cls(
            cobros=RepositorioCobroPostgres(unidad.sesion),
            recordatorios=RepositorioRecordatoriosPostgres(unidad.sesion),
            reembolsos=RepositorioReembolsoPostgres(unidad.sesion),
            aislamiento=AislamientoConSavepoint(unidad.sesion),
        )
