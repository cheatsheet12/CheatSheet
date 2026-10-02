"""El registro manual y la corrección de reembolsos (HU-E6-05 RN-07 y RN-08).

Ninguno habla con MercadoPago: la devolución de una transferencia la declara el administrador, y
un error de carga se corrige con una fila negativa visible. Van en una sola transacción cada uno,
con el cobro cargado **con bloqueo de fila** y la suma hecha por `aplicar`.

Los reembolsos por la API (dos transacciones, con clave de idempotencia) viven en
`reembolsos.py`; lo que comparten, en `reembolsos_comunes.py`.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from cheatsheet.contexts.payments.application.errors import (
    CobroInexistente,
    CobroNoReembolsable,
    ReembolsoNoCorregible,
)
from cheatsheet.contexts.payments.application.ports import (
    PortRepositorioCobro,
    PortRepositorioReembolso,
    PortSaldoDeComprobante,
)
from cheatsheet.contexts.payments.application.reembolsos_comunes import (
    aplicar,
    cargar_cobro,
    detalle_de_fila,
    exigir_administrador,
    publicar,
)
from cheatsheet.contexts.payments.domain.cobro import Cobro
from cheatsheet.contexts.payments.domain.reembolso import Reembolso
from cheatsheet.shared.auditoria import Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import InvarianteViolada
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.roles import RolUsuario


class RegistrarReembolsoManual:
    """HU-E6-05 RN-07 — la devolución de una transferencia, declarada a mano."""

    def __init__(
        self,
        *,
        cobros: PortRepositorioCobro,
        reembolsos: PortRepositorioReembolso,
        saldos: PortSaldoDeComprobante,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._cobros = cobros
        self._reembolsos = reembolsos
        self._saldos = saldos
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        cobro_id: UUID,
        monto: Decimal,
        dia: date,
        referencia: str | None,
        motivo: str,
        ahora: datetime,
    ) -> Cobro:
        del empresa_id
        exigir_administrador(rol)
        cobro = await cargar_cobro(self._cobros, cobro_id)
        try:
            fila = cobro.registrar_reembolso_manual(
                reembolso_id=uuid4(),
                monto=monto,
                dia=dia,
                referencia=referencia,
                motivo=motivo,
                usuario_id=usuario_id,
                ahora=ahora,
            )
        except InvarianteViolada as exc:
            raise CobroNoReembolsable(str(exc)) from exc
        await aplicar(
            cobros=self._cobros,
            reembolsos=self._reembolsos,
            saldos=self._saldos,
            cobro=cobro,
            fila=fila,
        )
        await publicar(
            self._publicador,
            cobro=cobro,
            usuario_id=usuario_id,
            ahora=ahora,
            accion="registrar_reembolso_manual",
            resultado=Resultado.COMPLETADO,
            detalle=detalle_de_fila(fila),
        )
        return cobro


class CorregirReembolso:
    """HU-E6-05 RN-08 — un error de carga se corrige con una fila negativa visible.

    El estado se recalcula del acumulado, así que una corrección puede **bajarlo**
    (`REEMBOLSADO → REEMBOLSADO_PARCIAL → APROBADO`). El índice único sobre `corrige_a` cierra la
    carrera de dos correcciones simultáneas.
    """

    def __init__(
        self,
        *,
        cobros: PortRepositorioCobro,
        reembolsos: PortRepositorioReembolso,
        saldos: PortSaldoDeComprobante,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._cobros = cobros
        self._reembolsos = reembolsos
        self._saldos = saldos
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        cobro_id: UUID,
        reembolso_id: UUID,
        motivo: str,
        ahora: datetime,
    ) -> Cobro:
        del empresa_id
        exigir_administrador(rol)
        cobro = await cargar_cobro(self._cobros, cobro_id)
        original = await self._reembolsos.buscar_por_id(reembolso_id)
        if original is None or original.cobro_id != cobro.id:
            raise CobroInexistente("El reembolso no existe")
        historial = await self._reembolsos.de_cobro(cobro.id)
        try:
            fila = cobro.corregir_reembolso(
                original,
                reembolso_id=uuid4(),
                ya_corregido=any(uno.corrige_a == original.id for uno in historial),
                motivo=motivo,
                usuario_id=usuario_id,
                ahora=ahora,
            )
        except InvarianteViolada as exc:
            raise ReembolsoNoCorregible(str(exc)) from exc
        await aplicar(
            cobros=self._cobros,
            reembolsos=self._reembolsos,
            saldos=self._saldos,
            cobro=cobro,
            fila=fila,
        )
        await publicar(
            self._publicador,
            cobro=cobro,
            usuario_id=usuario_id,
            ahora=ahora,
            accion="corregir_reembolso",
            resultado=Resultado.COMPLETADO,
            detalle=detalle_de_fila(fila) | {"corrige_a": str(original.id)},
        )
        return cobro


class VerReembolsos:
    """El historial de un cobro (PAN-COB-02). Todos los roles leen (HU-E6-01 RN-04)."""

    def __init__(self, reembolsos: PortRepositorioReembolso) -> None:
        self._reembolsos = reembolsos

    async def ejecutar(self, cobro_id: UUID) -> list[Reembolso]:
        return await self._reembolsos.de_cobro(cobro_id)


__all__ = ["CorregirReembolso", "RegistrarReembolsoManual", "VerReembolsos"]
