"""Where the browser is sent to authorize. No network, just a query string.

A port anyway, because the client id and MercadoPago's host are configuration, and a use
case that read them would be reaching into `platform/`.
"""

from __future__ import annotations

from urllib.parse import urlencode

from cheatsheet.contexts.integrations.application.ports import PedidoDeAutorizacion
from cheatsheet.contexts.integrations.infrastructure.mercadopago.cliente import (
    ConfiguracionMercadoPago,
)

#: MercadoPago requires it and documents a single value. Sent explicitly rather than
#: relying on a default that could change.
PLATAFORMA = "mp"

#: The only PKCE method MercadoPago accepts, and the only one worth using: `plain` would
#: put the verifier in the URL, which is the thing PKCE exists to avoid.
METODO_DE_DESAFIO = "S256"


class AutorizacionMercadoPago:
    """Implements `PortAutorizacionOAuth`."""

    def __init__(self, config: ConfiguracionMercadoPago) -> None:
        self._config = config

    def url_de_autorizacion(self, pedido: PedidoDeAutorizacion) -> str:
        parametros = {
            "client_id": self._config.client_id,
            "response_type": "code",
            "platform_id": PLATAFORMA,
            "state": pedido.estado,
            # The same value has to be repeated when the code is exchanged, and
            # MercadoPago compares them. Both come from this one setting so they cannot
            # drift apart.
            "redirect_uri": self._config.redirect_uri,
            "code_challenge": pedido.desafio,
            "code_challenge_method": METODO_DE_DESAFIO,
        }
        return f"{self._config.auth_url.rstrip('/')}/authorization?{urlencode(parametros)}"
