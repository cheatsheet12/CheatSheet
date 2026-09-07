"""Donde `payments` recibe su acceso a MercadoPago, a `billing` y a `business_config`.

La misma forma que `padron.py` y `arca.py`, y por la misma razón: acá se encuentran contextos,
y la infraestructura de uno no puede meter mano en la de otro (R3). El ensamblado ocurre en el
composition root, por encima de todos.

Cuatro piezas se arman acá:

- **El token de MercadoPago**, que sale de `integrations` — el OAuth y su refresco ya existen
  desde el épico 2, y este módulo sólo pide la credencial vigente.
- **La pasarela**, real o simulada según el `*_ADAPTADOR` de siempre.
- **El saldo de un comprobante**, que sale de `billing` (HU-E6-06).
- **La cadena de recordatorios**, que sale de `business_config` (HS-T3).

Se construyen **por request** y no cacheadas por proceso: las tres primeras están atadas a una
transacción —el token puede tener que refrescarse, y refrescarlo persiste— y la cuarta lee una
fila de la empresa actual. Es la misma conclusión a la que llegó `arca.py`.
"""

from __future__ import annotations

from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.contexts.billing.infrastructure.repositorio_comprobante import (
    RepositorioComprobantePostgres,
)
from cheatsheet.contexts.business_config.application.reglas import ConsultarReglasVigentes
from cheatsheet.contexts.business_config.infrastructure.ensamblado import (
    ConfiguracionDeNegocio,
)
from cheatsheet.contexts.integrations.application.errors import (
    ConexionRechazada,
    ProveedorNoDisponible,
)
from cheatsheet.contexts.integrations.domain.valores import SistemaExterno
from cheatsheet.contexts.integrations.infrastructure.ensamblado import Integraciones
from cheatsheet.contexts.payments.application.errors import PasarelaNoDisponible
from cheatsheet.contexts.payments.application.ports import (
    PortCadenaDeEscalamiento,
    PortPasarelaDePago,
    PortSaldoDeComprobante,
)
from cheatsheet.contexts.payments.infrastructure.cadena import CadenaViaConfiguracion
from cheatsheet.contexts.payments.infrastructure.envio import EnvioPorConsola
from cheatsheet.contexts.payments.infrastructure.pasarela import (
    PasarelaMercadoPago,
    PasarelaSimulada,
    PortTokenDeMercadoPago,
)
from cheatsheet.contexts.payments.infrastructure.saldo import SaldoViaBilling
from cheatsheet.platform.settings import AdaptadorDeMercadoPago, Settings
from cheatsheet.shared.empresa import EmpresaId


class TokenDesdeIntegraciones(PortTokenDeMercadoPago):
    """El access token vigente de una empresa, resuelto por `integrations`.

    Todo lo que puede salir mal se aplana a `PasarelaNoDisponible`, y ese aplanado es
    deliberado: para quien está intentando cobrar, «la cuenta no está conectada», «el token
    venció» y «MercadoPago no contesta» son un solo hecho accionable — no podemos cobrar
    ahora — y ninguno dice nada sobre el cobro en sí.
    """

    def __init__(self, *, integraciones: Integraciones) -> None:
        self._piezas = integraciones

    async def para(self, empresa_id: EmpresaId) -> str:
        configuracion = await self._piezas.integraciones.buscar(
            empresa_id, SistemaExterno.MERCADOPAGO
        )
        if configuracion is None:
            # El caso ordinario recién salido del onboarding, no una anomalía: la empresa
            # todavía no conectó su cuenta.
            raise PasarelaNoDisponible(
                "La empresa no tiene conectada la integracion con MercadoPago"
            )

        try:
            credencial = self._piezas.cifrado.descifrar(configuracion.credencial)
        except (ProveedorNoDisponible, ConexionRechazada) as exc:
            raise PasarelaNoDisponible(
                f"No se pudo leer la credencial de MercadoPago: {exc}"
            ) from exc

        acceso, _ = _desempaquetar(credencial)
        return acceso


def _desempaquetar(credencial: bytes) -> tuple[str, str]:
    """El par acceso/refresco que `integrations` guarda para MercadoPago.

    Mismo formato de dos líneas que el ticket de ARCA, y leído acá con el helper que el otro
    contexto publica en su capa de aplicación — que es donde vive el contrato del Open Host
    Service y donde R3 permite leerlo.
    """
    from cheatsheet.contexts.integrations.application.ticket import desempaquetar

    return desempaquetar(credencial)


def armar_pasarela(unidad: UnidadDeTrabajo, settings: Settings) -> PortPasarelaDePago:
    """MercadoPago, real o simulado según `MERCADOPAGO_ADAPTADOR`."""
    if settings.mercadopago_adaptador is AdaptadorDeMercadoPago.MERCADOPAGO:
        return PasarelaMercadoPago(
            tokens=TokenDesdeIntegraciones(
                integraciones=Integraciones.armar(unidad.sesion, settings)
            )
        )
    return PasarelaSimulada(settings.entorno)


def armar_saldos(unidad: UnidadDeTrabajo) -> PortSaldoDeComprobante:
    """El saldo de un comprobante, como `payments` lo ve (HU-E6-06)."""
    return SaldoViaBilling(RepositorioComprobantePostgres(unidad.sesion))


def armar_cadena(unidad: UnidadDeTrabajo) -> PortCadenaDeEscalamiento:
    """La cadena de recordatorios, como `payments` la ve (HS-T3)."""
    piezas = ConfiguracionDeNegocio.armar(unidad)
    return CadenaViaConfiguracion(ConsultarReglasVigentes(piezas.reglas))


def armar_envio(settings: Settings) -> EnvioPorConsola:
    """Por dónde sale un recordatorio.

    **Hoy siempre es la consola**, y decirlo es más honesto que esconderlo detrás de un
    switch que tiene una sola posición: el canal real es WhatsApp y lo construye el épico 8.
    El adaptador se niega a arrancar en producción, así que este pendiente no se puede
    desplegar sin que alguien se entere.
    """
    return EnvioPorConsola(settings.entorno)


__all__ = [
    "TokenDesdeIntegraciones",
    "armar_cadena",
    "armar_envio",
    "armar_pasarela",
    "armar_saldos",
]
