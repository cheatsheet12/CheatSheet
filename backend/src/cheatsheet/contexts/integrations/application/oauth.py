"""The two halves of an OAuth2 authorization (HU-E2-02 RN-01).

The protocol is split because the user leaves: the browser goes to MercadoPago, a person
presses "Authorize" there, and the answer comes back as a redirect minutes later. Nothing
in between is under our control, which is why both halves exist as separate use cases
instead of one.

**What holds the two halves together is the `state`, and that is a business rule.** It is
issued for one company, stored where only this system can read it, and consumed exactly
once. Without it, anyone who gets an Administrator to open a crafted link attaches *their*
MercadoPago account to somebody else's company — and from then on every payment link of
epic 6 collects into the wrong account. That is why the check lives here and not in the
router: a rule whose failure moves money does not belong at the HTTP edge.

PKCE (RFC 7636) sits on top: what travels to the provider is a hash, and the secret behind
it stays here until the code is exchanged. It costs a hash and makes a stolen
authorization code useless to whoever stole it.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass

from cheatsheet.contexts.integrations.application.errors import (
    AutorizacionInvalida,
    SistemaNoConfigurable,
)
from cheatsheet.contexts.integrations.application.integraciones import (
    ConectarIntegracion,
    VistaDeIntegracion,
    exigir_administrador,
)
from cheatsheet.contexts.integrations.application.ports import (
    AutorizacionPendiente,
    PedidoDeAutorizacion,
    PortMemoriaDeAutorizacion,
    PortRegistroDeAdaptadores,
)
from cheatsheet.contexts.integrations.domain.valores import CLAVE_VERIFICADOR, SistemaExterno
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.roles import RolUsuario

#: Bytes of entropy behind the `state` and the PKCE verifier. 32 is what RFC 7636 §7.1
#: asks for as a minimum and what `secrets.token_urlsafe` turns into 43 characters.
BYTES_DE_ENTROPIA = 32

#: How long an authorization may stay in flight. Ten minutes is longer than anyone takes
#: to press a button and shorter than a tab left open over lunch — which is the case this
#: window exists to expire.
TTL_POR_DEFECTO_SEGUNDOS = 600

GeneradorDeSecreto = Callable[[], str]


def _secreto() -> str:
    return secrets.token_urlsafe(BYTES_DE_ENTROPIA)


def desafio_de(verificador: str) -> str:
    """The PKCE `code_challenge` for a verifier: base64url(sha256), unpadded.

    Unpadded because RFC 7636 §4.2 says so, and a provider that receives the `=` padding
    computes a different challenge and rejects the exchange — with a message about the
    code, not about the padding.
    """
    resumen = hashlib.sha256(verificador.encode("ascii")).digest()
    return base64.urlsafe_b64encode(resumen).decode("ascii").rstrip("=")


@dataclass(frozen=True, slots=True)
class AutorizacionIniciada:
    """Where to send the browser, and how long that link is good for."""

    url: str
    expira_en_segundos: int


class IniciarAutorizacion:
    """First half: mint the secrets, remember them, and hand back the URL.

    Administrador only. An Operador may look at the integrations screen (HU-E2-05) and may
    press "Verificar estado", but connecting an account that will collect money is not a
    read.
    """

    def __init__(
        self,
        *,
        adaptadores: PortRegistroDeAdaptadores,
        memoria: PortMemoriaDeAutorizacion,
        ttl_segundos: int = TTL_POR_DEFECTO_SEGUNDOS,
        generador: GeneradorDeSecreto = _secreto,
    ) -> None:
        self._adaptadores = adaptadores
        self._memoria = memoria
        self._ttl = ttl_segundos
        self._generador = generador

    async def ejecutar(
        self, *, empresa_id: EmpresaId, rol: RolUsuario, sistema: SistemaExterno
    ) -> AutorizacionIniciada:
        exigir_administrador(rol)
        autorizacion = self._adaptadores.autorizacion(sistema)
        if autorizacion is None:
            raise SistemaNoConfigurable(
                f"La conexion de {sistema.value} no se hace con una autorizacion OAuth2"
            )

        estado = self._generador()
        verificador = self._generador()
        await self._memoria.guardar(
            estado,
            AutorizacionPendiente(empresa_id=empresa_id, sistema=sistema, verificador=verificador),
            self._ttl,
        )
        url = autorizacion.url_de_autorizacion(
            PedidoDeAutorizacion(estado=estado, desafio=desafio_de(verificador))
        )
        return AutorizacionIniciada(url=url, expira_en_segundos=self._ttl)


class CompletarAutorizacion:
    """Second half: check what came back, then connect with it.

    Delegates to `ConectarIntegracion` rather than reimplementing it, so a credential
    obtained through OAuth is stored, encrypted, audited and made idempotent by exactly
    the same code as one typed into a form.
    """

    def __init__(
        self, *, memoria: PortMemoriaDeAutorizacion, conectar: ConectarIntegracion
    ) -> None:
        self._memoria = memoria
        self._conectar = conectar

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        rol: RolUsuario,
        sistema: SistemaExterno,
        codigo: str,
        estado: str,
        usuario_id: UsuarioId | None = None,
        direccion_ip: str | None = None,
    ) -> VistaDeIntegracion:
        # Before the `state` is spent: a request that was never going to be allowed must
        # not consume a one-shot token and force the Administrator to start again.
        exigir_administrador(rol)
        if not codigo.strip():
            raise AutorizacionInvalida("La autorizacion volvio sin codigo")

        pendiente = await self._memoria.consumir(estado)
        if pendiente is None:
            raise AutorizacionInvalida(
                "La autorizacion vencio o ya fue usada. Volve a iniciar la conexion"
            )
        # The company that comes back must be the company that left. One message for both
        # mismatches on purpose — see `AutorizacionInvalida`.
        if pendiente.empresa_id != empresa_id or pendiente.sistema is not sistema:
            raise AutorizacionInvalida("Esta autorizacion no corresponde a esta conexion")

        return await self._conectar.ejecutar(
            empresa_id=empresa_id,
            rol=rol,
            sistema=sistema,
            contenido=codigo.encode("utf-8"),
            efimeros={CLAVE_VERIFICADOR: pendiente.verificador},
            usuario_id=usuario_id,
            direccion_ip=direccion_ip,
        )
