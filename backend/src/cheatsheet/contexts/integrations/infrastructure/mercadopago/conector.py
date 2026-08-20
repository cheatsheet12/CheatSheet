"""Connecting a MercadoPago account, and keeping it connected (HU-E2-02).

One class for two ports. `PortConectorDeIntegracion` and `PortRenovacionDeCredencial` are
the same conversation at two moments — a code or a refresh token goes in, a pair of tokens
comes back — and splitting them across two classes would duplicate the mapping without
separating anything.

**The order in `conectar` is RN-02's rule**: the code is exchanged, and the account is
read *before* anything is declared connected. An exchange that works only proves the code
was valid; reading `/users/me` is what proves the token we are about to store actually
speaks for an account.
"""

from __future__ import annotations

from cheatsheet.contexts.integrations.application.errors import ConexionRechazada
from cheatsheet.contexts.integrations.application.ports import (
    MaterialDeConexion,
    ResultadoDeConexion,
)
from cheatsheet.contexts.integrations.domain.valores import CLAVE_VERIFICADOR, EstadoDeConexion
from cheatsheet.contexts.integrations.infrastructure.mercadopago.cliente import ClienteMercadoPago
from cheatsheet.contexts.integrations.infrastructure.mercadopago.mapeo import (
    desempaquetar,
    empaquetar,
    estado_por_ambiente,
    leer_tokens,
    parametros_de,
)
from cheatsheet.shared.clock import Reloj


class ConectorMercadoPago:
    """Implements `PortConectorDeIntegracion` and `PortRenovacionDeCredencial`."""

    def __init__(self, cliente: ClienteMercadoPago, reloj: Reloj, *, es_produccion: bool) -> None:
        self._cliente = cliente
        self._reloj = reloj
        self._es_produccion = es_produccion

    async def conectar(self, material: MaterialDeConexion) -> ResultadoDeConexion:
        codigo = material.contenido.decode("utf-8", errors="ignore").strip()
        if not codigo:
            raise ConexionRechazada("La autorizacion de MercadoPago volvio sin codigo")
        verificador = material.efimeros.get(CLAVE_VERIFICADOR, "").strip()
        if not verificador:
            # Only `CompletarAutorizacion` can supply this, so its absence means the code
            # arrived through some other path — which is exactly what PKCE is guarding.
            raise ConexionRechazada("Esta autorizacion de MercadoPago no puede completarse")

        datos = await self._cliente.canjear(codigo=codigo, verificador=verificador)
        tokens = leer_tokens(datos, self._reloj.ahora())
        estado, detalle = estado_por_ambiente(tokens.cuenta_real, self._es_produccion)
        if estado is EstadoDeConexion.NO_CONECTADO:
            raise ConexionRechazada(detalle or "La cuenta de MercadoPago no corresponde")

        cuenta = await self._cliente.cuenta(acceso=tokens.acceso)
        return ResultadoDeConexion(
            credencial=empaquetar(tokens.acceso, tokens.refresco),
            estado=estado,
            detalle=detalle,
            parametros=parametros_de(tokens, cuenta),
        )

    async def renovar(self, credencial: bytes) -> ResultadoDeConexion:
        """Trade the stored refresh token for a fresh pair.

        **A mismatch found here never disconnects.** `estado_por_ambiente` refuses a real
        account outside production, which is right when somebody is connecting one; at
        renewal time that same finding would mean the deployment moved underneath an
        integration that has been working, and dropping a working connection over it would
        be the wrong call. It becomes `ATENCION` — visible, and still usable.
        """
        _, refresco = desempaquetar(credencial)
        datos = await self._cliente.refrescar(refresco=refresco)
        tokens = leer_tokens(datos, self._reloj.ahora())
        estado, detalle = estado_por_ambiente(tokens.cuenta_real, self._es_produccion)
        if estado is EstadoDeConexion.NO_CONECTADO:
            estado = EstadoDeConexion.ATENCION
        return ResultadoDeConexion(
            credencial=empaquetar(tokens.acceso, tokens.refresco),
            estado=estado,
            detalle=detalle,
            parametros=parametros_de(tokens),
        )
