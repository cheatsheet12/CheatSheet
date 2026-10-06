"""Lo que comparten los casos de uso de reembolso: el guarda, la carga con bloqueo, la única
forma de sumar plata y la bitácora.

**`aplicar` es la única función que suma plata**: fila, acumulado y saldo del comprobante, juntos
y en la misma transacción. Tres caminos (API, manual, corrección), una sola forma de sumar.

A la bitácora va el monto, el origen, el id y el motivo **de MercadoPago** cuando lo hay;
**nunca** la referencia bancaria ni datos del pagador (`CLAUDE.md` §3.6).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from cheatsheet.contexts.payments.application.cobros import MOTIVO_SOLO_ADMIN_REEMBOLSA
from cheatsheet.contexts.payments.application.errors import CobroInexistente
from cheatsheet.contexts.payments.application.ports import (
    PortRepositorioCobro,
    PortRepositorioReembolso,
    PortSaldoDeComprobante,
)
from cheatsheet.contexts.payments.domain.cobro import Cobro
from cheatsheet.contexts.payments.domain.reembolso import Reembolso
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.roles import RolUsuario


def exigir_administrador(rol: RolUsuario) -> None:
    if rol is not RolUsuario.ADMINISTRADOR:
        raise EntradaInvalida(MOTIVO_SOLO_ADMIN_REEMBOLSA)


async def cargar_cobro(cobros: PortRepositorioCobro, cobro_id: UUID) -> Cobro:
    """El cobro **con bloqueo de fila**: todo camino que suma plata lo carga así."""
    cobro = await cobros.buscar_para_actualizar(cobro_id)
    if cobro is None:
        raise CobroInexistente("El cobro no existe")
    return cobro


async def aplicar(
    *,
    cobros: PortRepositorioCobro,
    reembolsos: PortRepositorioReembolso,
    saldos: PortSaldoDeComprobante,
    cobro: Cobro,
    fila: Reembolso,
) -> None:
    """Fila + acumulado + saldo, en la misma transacción. **La única forma de sumar plata.**"""
    await reembolsos.agregar(fila)
    await cobros.guardar(cobro)
    if cobro.comprobante_id is not None:
        await saldos.registrar_reembolso(cobro.comprobante_id, fila.monto)


async def publicar(
    publicador: PublicadorDeEventos,
    *,
    cobro: Cobro,
    usuario_id: UsuarioId,
    ahora: datetime,
    accion: str,
    resultado: Resultado,
    detalle: dict[str, str],
) -> None:
    await publicador.publicar(
        EventoAuditable(
            evento_id=uuid4(),
            empresa_id=cobro.empresa_id,
            ocurrido_en=ahora,
            usuario_id=usuario_id,
            modulo=Modulo.PAYMENTS,
            accion=accion,
            entidad_afectada=f"Cobro:{cobro.id}",
            resultado=resultado,
            detalle=detalle,
        )
    )


def detalle_de_fila(fila: Reembolso) -> dict[str, str]:
    return {
        "monto": str(fila.monto),
        "origen": fila.origen.value,
        "reembolso_id": str(fila.id),
    }


__all__ = [
    "aplicar",
    "cargar_cobro",
    "detalle_de_fila",
    "exigir_administrador",
    "publicar",
]
