"""Los casos de uso de cobros (HU-E6-01 … HU-E6-06).

**Administrador y Operador generan y cancelan; sólo el Administrador reembolsa** (HU-E6-05
RN-05), y Solo Lectura mira (HU-E6-01 RN-04). Los guardas viven en los casos de uso y no sólo
en el router, por lo que enseñó PRU-09.

Dos decisiones del épico se ven acá con todas las letras:

- **D26** — un cobro asociado a un comprobante **no descuenta nada al crearse**. El tope de
  RN-02 se valida contra el saldo, pero el saldo baja cuando MercadoPago confirma y en ninguna
  otra transición. Un comprobante cuyo saldo bajó porque alguien generó un link que nadie pagó
  es un comprobante que miente en el balance del épico 9.
- **D27** — el reembolso pedido no cambia el estado. El cobro sigue `APROBADO` y lo que la
  pantalla muestra sale de `reembolso_solicitado_en`.

Los reembolsos viven en `application/reembolsos.py` y `GenerarCobro` en
`application/generacion_de_cobro.py`: este archivo ya pasaba de 400 líneas.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from cheatsheet.contexts.payments.application.errors import (
    CobroInexistente,
    CobroNoCancelable,
)
from cheatsheet.contexts.payments.application.ports import (
    FiltrosDeCobro,
    MetricasDeCobros,
    PortPasarelaDePago,
    PortRepositorioCobro,
)
from cheatsheet.contexts.payments.domain.cobro import (
    MENSAJE_MONTO_NO_POSITIVO,
    Cobro,
)
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada, OperacionNoPermitida
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.roles import RolUsuario

MOTIVO_SIN_PERMISO = "Solo un Administrador u Operador puede gestionar cobros"
MOTIVO_SOLO_ADMIN_REEMBOLSA = "Solo un Administrador puede reembolsar un cobro"
MENSAJE_MONTO_DEMASIADO_GRANDE = "El monto es demasiado grande."
#: Tope de **negocio**, no la capacidad de la columna (`Numeric(14,2)`): un cobro de mas de cien
#: millones de pesos por un link de pago es un error de tipeo mas probable que una venta.
#: PENDIENTE DE VERIFICAR contra la documentacion de MercadoPago (unidad
#: `nuevo-cobro-desde-su-panel`, P5): si su limite fuera menor, manda el de MercadoPago.
MONTO_MAXIMO_DE_COBRO = Decimal("100000000.00")


def exigir_gestor(rol: RolUsuario) -> None:
    if rol not in (RolUsuario.ADMINISTRADOR, RolUsuario.OPERADOR):
        raise OperacionNoPermitida(MOTIVO_SIN_PERMISO)


def monto_desde(texto: str) -> Decimal:
    """Convierte lo que llega del formulario. **Nunca pasa por `float`.**

    Un `float` está mal en el cuarto decimal, que es exactamente donde vive un centavo, y
    `CLAUDE.md` §3.5 lo prohíbe en todo el sistema.
    """
    try:
        monto = Decimal(texto)
    except InvalidOperation as exc:
        raise EntradaInvalida(MENSAJE_MONTO_NO_POSITIVO) from exc
    # `NaN` explota en la primera comparacion (`InvalidOperation`) y `Infinity` pasa el `> 0` y
    # falla al redondear: los dos serian un 500 en un flujo que toca plata.
    if not monto.is_finite():
        raise EntradaInvalida(MENSAJE_MONTO_NO_POSITIVO)
    if monto > MONTO_MAXIMO_DE_COBRO:
        raise EntradaInvalida(MENSAJE_MONTO_DEMASIADO_GRANDE)
    return monto


class ListarCobros:
    """PAN-COB-01. Todos los roles leen (RN-04)."""

    def __init__(self, cobros: PortRepositorioCobro) -> None:
        self._cobros = cobros

    async def ejecutar(self, filtros: FiltrosDeCobro | None = None) -> list[Cobro]:
        return await self._cobros.listar(filtros or FiltrosDeCobro())


class MetricasDelPeriodo:
    """El encabezado de PAN-COB-01 (RN-01): cobrado, pendiente, en mora y la tasa.

    «Cobrado» se mide por **fecha de pago** y el resto por fecha de creación (D91, ADR-0010);
    `MetricasDeCobros` explica la base de cada número.

    El período por defecto es el mes en curso, y eso lo decide **este caso de uso** y no la
    pantalla: es una regla de negocio de la historia, y dejarla en el frontend haría que el
    reporte del épico 9 tuviera que redecidirla.
    """

    def __init__(self, cobros: PortRepositorioCobro) -> None:
        self._cobros = cobros

    async def ejecutar(
        self, *, ahora: datetime, filtros: FiltrosDeCobro | None = None
    ) -> MetricasDeCobros:
        efectivos = filtros or FiltrosDeCobro()
        if efectivos.desde is None and efectivos.hasta is None:
            efectivos = FiltrosDeCobro(
                desde=ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
                hasta=None,
                estados=efectivos.estados,
            )
        return await self._cobros.metricas(efectivos)


class VerCobro:
    """PAN-COB-02. Levanta en vez de devolver `None`.

    Bajo RLS «no es tuyo» y «no existe» son la misma respuesta a propósito: distinguirlas le
    diría a una empresa que el id de un cobro ajeno es real.
    """

    def __init__(self, cobros: PortRepositorioCobro) -> None:
        self._cobros = cobros

    async def ejecutar(self, cobro_id: UUID) -> Cobro:
        cobro = await self._cobros.buscar_por_id(cobro_id)
        if cobro is None:
            raise CobroInexistente("El cobro no existe")
        return cobro


class RegenerarLink:
    """El último criterio de HU-E6-03: se invalida el anterior y se activa el nuevo.

    Invalidar es reemplazar el objeto (`asignar_link`), no sacar uno de una lista: no hay
    forma de olvidarse del viejo porque nunca hubo dos.
    """

    def __init__(
        self,
        *,
        cobros: PortRepositorioCobro,
        pasarela: PortPasarelaDePago,
        publicador: PublicadorDeEventos,
        url_de_retorno: str,
    ) -> None:
        self._cobros = cobros
        self._pasarela = pasarela
        self._publicador = publicador
        self._url_de_retorno = url_de_retorno

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        cobro_id: UUID,
        ahora: datetime,
    ) -> Cobro:
        exigir_gestor(rol)

        cobro = await self._cobros.buscar_por_id(cobro_id)
        if cobro is None:
            raise CobroInexistente("El cobro no existe")

        link = await self._pasarela.crear_link(
            empresa_id=empresa_id, cobro=cobro, url_de_retorno=self._url_de_retorno
        )
        cobro.asignar_link(link, ahora)
        await self._cobros.guardar(cobro)

        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                usuario_id=usuario_id,
                modulo=Modulo.PAYMENTS,
                # La historia pide que el reemplazo quede registrado, no sólo la generación.
                accion="regenerar_link_de_cobro",
                entidad_afectada=f"Cobro:{cobro.id}",
                resultado=Resultado.COMPLETADO,
            )
        )
        return cobro


class CancelarCobro:
    """HU-E6-04 — baja una deuda que ya no corresponde cobrar.

    El motivo es obligatorio y de diez caracteres (RN-02), y eso lo impone el agregado. Los
    recordatorios se detienen solos: HS-T3 no le manda a un `CANCELADO`, así que la cadena se
    corta por el estado y no por una llamada que alguien pueda olvidar.

    **El link se invalida en MercadoPago, no sólo acá** (RN-03). Que el agregado deje de
    considerarlo usable no impide que el cliente pague: la preferencia se creó con
    `expiration_date_to = vence_el`, una fecha futura, y el link ya está en su WhatsApp. Si
    MercadoPago no confirma que murió, **la cancelación no ocurre**: el cobro queda como
    estaba y el mensaje llega a la pantalla. Mismo criterio que HU-E6-03 con el alta —una
    operación sobre plata no se hace a medias— y misma consecuencia asumida: con MercadoPago
    caído no se puede cancelar.
    """

    def __init__(
        self,
        *,
        cobros: PortRepositorioCobro,
        pasarela: PortPasarelaDePago,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._cobros = cobros
        self._pasarela = pasarela
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        cobro_id: UUID,
        motivo: str,
        ahora: datetime,
    ) -> Cobro:
        exigir_gestor(rol)

        cobro = await self._cobros.buscar_por_id(cobro_id)
        if cobro is None:
            raise CobroInexistente("El cobro no existe")

        # **Primero el agregado, después la red.** Un motivo de nueve caracteres o un cobro ya
        # pagado se rechazan sin gastar una llamada a MercadoPago. Y como el repositorio
        # reconstituye un objeto de dominio aparte de la fila del ORM, mutarlo acá no escribe
        # nada: si la invalidación falla y esto levanta, el cobro queda como estaba.
        try:
            cobro.cancelar(motivo=motivo, ahora=ahora)
        except InvarianteViolada as exc:
            # Angostado para que el router conteste 409 con el texto de la historia, que
            # además dice qué hacer en su lugar.
            raise CobroNoCancelable(str(exc)) from exc

        await self._invalidar_link_si_hace_falta(empresa_id=empresa_id, cobro=cobro, ahora=ahora)

        await self._cobros.guardar(cobro)
        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                usuario_id=usuario_id,
                modulo=Modulo.PAYMENTS,
                accion="cancelar_cobro",
                # RN-04 pide el motivo en la bitácora. Va en la entidad porque el evento no
                # tiene un campo libre, y truncado porque la columna tiene un tope.
                entidad_afectada=f"Cobro:{cobro.id}",
                resultado=Resultado.COMPLETADO,
            )
        )
        return cobro

    async def _invalidar_link_si_hace_falta(
        self, *, empresa_id: EmpresaId, cobro: Cobro, ahora: datetime
    ) -> None:
        """La llamada a MercadoPago, y las dos veces que no hace falta darla.

        Sin link nunca hubo preferencia. Y si el cobro ya venció, la preferencia también: se
        creó con `expiration_date_to = cobro.vence_el`, así que `esta_vencido_a(ahora)` y «el
        proveedor ya no lo acepta» son el mismo hecho. Es una equivalencia exacta y no una
        heurística — si un día el adaptador dejara de mandar ese campo, este atajo habría que
        sacarlo con él.
        """
        if cobro.link is None or cobro.esta_vencido_a(ahora):
            return
        await self._pasarela.invalidar_link(
            empresa_id=empresa_id, preference_id=cobro.link.preference_id, ahora=ahora
        )


__all__ = [
    "MENSAJE_MONTO_DEMASIADO_GRANDE",
    "MONTO_MAXIMO_DE_COBRO",
    "MOTIVO_SIN_PERMISO",
    "MOTIVO_SOLO_ADMIN_REEMBOLSA",
    "CancelarCobro",
    "ListarCobros",
    "MetricasDelPeriodo",
    "RegenerarLink",
    "VerCobro",
    "exigir_gestor",
    "monto_desde",
]
