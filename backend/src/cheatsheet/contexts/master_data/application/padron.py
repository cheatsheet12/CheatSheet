"""Asking ARCA about a client's tax id, and what each answer is allowed to do.

HU-E4-01 RN-02 says the CUIT is validated against ARCA when a client is created or
edited, and that an invalid one blocks the save. Taken literally that would make the
customer catalogue depend on a fiscal certificate the company may never have loaded —
ARCA is an optional integration (epic 2), and a business that only wants to keep a
customer list would be locked out of its own screen.

So the rule is honoured the way `padron-y-datos-fiscales` already honoured the equivalent
one during onboarding, and the distinction is the same:

- **not found blocks.** ARCA was asked and said the tax id does not exist.
- **could not ask does not block.** ARCA has not been connected, the certificate expired,
  the service timed out. The client is saved and the screen says the CUIT was not
  validated.

Structural validation is separate and blocks in every case, with or without a network:
eleven digits and a correct check digit. That is where the story's «El CUIT debe contener
11 dígitos.» comes from, and it needs nobody's permission.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from cheatsheet.contexts.master_data.application.autorizacion import exigir_lectura
from cheatsheet.contexts.master_data.application.ports import (
    DatosFiscalesDePadron,
    PadronNoDisponible,
    PortPadron,
)
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.fiscal import CUIT, LARGO_CUIT
from cheatsheet.shared.roles import RolUsuario

#: The exact text of HU-E4-01's third acceptance criterion.
MENSAJE_LARGO_INVALIDO = "El CUIT debe contener 11 digitos."


class EstadoDeConsulta(StrEnum):
    """The three answers the form has to tell apart, because it shows three things."""

    ENCONTRADO = "ENCONTRADO"
    NO_ENCONTRADO = "NO_ENCONTRADO"
    NO_DISPONIBLE = "NO_DISPONIBLE"


@dataclass(frozen=True, slots=True)
class VistaDePadron:
    """What the form receives after asking about a CUIT."""

    estado: EstadoDeConsulta
    datos: DatosFiscalesDePadron | None = None
    #: Why it could not be asked, in words the user can act on. Never a stack trace and
    #: never the provider's raw fault: those go to the log.
    motivo: str | None = None


def cuit_desde(valor: str) -> CUIT:
    """Build a `CUIT`, failing the length case with the message the story specifies.

    The Shared Kernel's own message names the length it got («Un CUIT tiene 11 digitos,
    no 9»), which is better for a developer and is not what HU-E4-01 asks the screen to
    say. Checking the length here first is three lines of duplication bought in exchange
    for not rewording a value object that `identity` also raises.
    """
    digitos = "".join(c for c in valor if c.isdigit())
    if len(digitos) != LARGO_CUIT:
        raise EntradaInvalida(MENSAJE_LARGO_INVALIDO)
    return CUIT(digitos)


async def consultar_padron(
    padron: PortPadron, *, empresa_id: EmpresaId, cuit: CUIT
) -> VistaDePadron:
    """The one place the three outcomes are produced, shared by the button and the saves.

    A free function rather than a use case because it has no authorization of its own and
    writes nothing: the callers are already authorized, and duplicating this `try` in
    three of them is how two of them eventually stop telling *not found* apart from
    *could not ask*.
    """
    try:
        datos = await padron.consultar(empresa_id=empresa_id, cuit=str(cuit))
    except PadronNoDisponible as exc:
        return VistaDePadron(EstadoDeConsulta.NO_DISPONIBLE, motivo=str(exc))
    if datos is None:
        return VistaDePadron(EstadoDeConsulta.NO_ENCONTRADO)
    return VistaDePadron(EstadoDeConsulta.ENCONTRADO, datos=datos)


class ConsultarPadronParaCliente:
    """The lookup behind «Validar contra ARCA» in the client form. Writes nothing."""

    def __init__(self, *, padron: PortPadron) -> None:
        self._padron = padron

    async def ejecutar(self, *, empresa_id: EmpresaId, cuit: str, rol: RolUsuario) -> VistaDePadron:
        """Read permission is enough: nothing is stored and the answer is about a number.

        Structural validation happens before the call rather than after, so a typo never
        spends a request at ARCA.
        """
        exigir_lectura(rol)
        return await consultar_padron(self._padron, empresa_id=empresa_id, cuit=cuit_desde(cuit))
