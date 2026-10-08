"""Hallazgos de Gate 2 del tramo ii: la llamada a Meta sin E/S de base, el reloj real, el cobro
releído, un recordatorio por cobro por barrido (U7, S1, S2, N2, N7).

- **S1.** Leer el contacto y la plantilla pasó a `preparar`, **antes** de reservar. Un error de base
  ahí deshace el savepoint: no queda fila, el barrido sigue con los demás y el siguiente lo retoma.
  Antes ocurría después de reservar, fuera de todo savepoint: abortaba la transacción de la empresa y
  la fila quedaba `INCIERTO` sin que nada hubiera salido.
- **S2.** Las fechas que se escriben salen del reloj real, no del `ahora` del inicio del barrido.
- **N2.** Si el cobro se pagó o cerró entre la reserva y el envío, no se manda.
- **N7.** Un cobro recibe a lo sumo un recordatorio por barrido.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from cheatsheet.contexts.payments.application.ports_de_recordatorios import (
    MensajeListo,
    ResultadoDeEnvio,
)
from cheatsheet.contexts.payments.application.recordatorios import ResultadoDeBarrido
from cheatsheet.contexts.payments.domain.cobro import Cobro
from cheatsheet.contexts.payments.domain.recordatorio import (
    COBRO_CERRADO,
    INCIERTO,
    VENTANA_DE_ENVIO,
    EstadoEntrega,
)
from cheatsheet.shared.transaccion import DespachoNoPersistido

from tests.contexts.payments.application.dobles_de_reintento import (
    BARRIDO_1,
    EnvioGuionado,
    RecordatoriosConBitacora,
    _con_un_cobro,
    _escenario,
    transitoria,
)
from tests.contexts.payments.application.test_cobros_y_recordatorios import (
    EMPRESA,
    TransaccionFalsa,
    _cobro,
    _tres_cobros_vencidos,
)

pytestmark = pytest.mark.asyncio


def _falla_la_base_en(*posiciones: int, escenario_envio: EnvioGuionado) -> None:
    """Hace que `preparar` levante lo que levanta el aislamiento cuando la base rechaza."""

    def al_preparar() -> None:
        if escenario_envio.preparados in posiciones:
            raise DespachoNoPersistido("la base rechazó la lectura del contacto")

    escenario_envio._al_preparar = al_preparar


# ------------------------------------------------------------------ S1


async def test_se_prepara_antes_de_reservar_y_mandar_no_lee_nada() -> None:
    """El orden es el contrato: leer, escribir y confirmar, y recién entonces hablar con Meta."""
    escenario, _ = await _con_un_cobro()

    await escenario.barrer(BARRIDO_1)

    assert escenario.transaccion.bitacora == [
        "preparar",
        "agregar",
        "confirmar",
        "enviar",
        "guardar",
        "confirmar",
    ]
    assert escenario.envio.preparados == 1


async def test_un_error_de_base_al_preparar_no_deja_fila_ni_voltea_a_los_demas() -> None:
    escenario = _escenario()
    _falla_la_base_en(2, escenario_envio=escenario.envio)
    primero, segundo, tercero = await _tres_cobros_vencidos(escenario.cobros)

    resultado = await escenario.barrer(BARRIDO_1)

    # El segundo no reservó nada: ni fila ni envío. Los otros dos salieron.
    assert {uno.cobro_id for uno in escenario.recordatorios.guardados} == {primero.id, tercero.id}
    assert [cobro_id for cobro_id, _ in escenario.envio.enviados] == [primero.id, tercero.id]
    assert resultado.procesados == 2
    assert resultado.fallidos == 0

    # El barrido siguiente lo evalúa como un paso nuevo y lo manda: nunca fue `INCIERTO`.
    await escenario.barrer(BARRIDO_1 + timedelta(hours=1))
    por_cobro = {uno.cobro_id: uno for uno in escenario.recordatorios.guardados}
    assert por_cobro[segundo.id].estado_entrega is EstadoEntrega.ENVIADO
    assert por_cobro[segundo.id].ultimo_error is None
    assert escenario.envio.llamadas == 3


async def test_un_error_de_base_al_preparar_un_reintento_deja_la_fila_como_estaba() -> None:
    escenario, _ = await _con_un_cobro(transitoria("131056"))
    await escenario.barrer(BARRIDO_1)
    antes = escenario.fila
    _falla_la_base_en(2, escenario_envio=escenario.envio)

    await escenario.barrer(BARRIDO_1 + timedelta(hours=1))

    # Sin intento contado, sin ventana abierta: el reintento sigue esperando, sin `INCIERTO`.
    assert escenario.fila == antes
    assert escenario.envio.llamadas == 1

    await escenario.barrer(BARRIDO_1 + timedelta(hours=2))
    assert escenario.envio.llamadas == 2
    assert escenario.fila.estado_entrega is EstadoEntrega.ENVIADO
    assert escenario.fila.intentos == 2


async def test_un_adaptador_que_levanta_al_preparar_no_voltea_el_barrido() -> None:
    """Un adaptador que rompe su contrato: no hay fila y los demás cobros siguen."""
    escenario = _escenario()

    def rompe() -> None:
        if escenario.envio.preparados == 1:
            raise RuntimeError("rompió el contrato")

    escenario.envio._al_preparar = rompe
    await _tres_cobros_vencidos(escenario.cobros)

    resultado = await escenario.barrer(BARRIDO_1)

    assert len(escenario.recordatorios.guardados) == 2
    assert resultado.procesados == 2


async def test_un_cobro_sin_telefono_queda_fallido_sin_llamar_a_meta() -> None:
    """`preparar` ya sabe que no puede salir: la fila se reserva y se registra, sin `mandar`."""
    escenario, _ = await _con_un_cobro()

    async def sin_telefono(**_: object) -> MensajeListo | ResultadoDeEnvio:
        return ResultadoDeEnvio(estado=EstadoEntrega.FALLIDO, codigo="SIN_TELEFONO")

    escenario.envio.preparar = sin_telefono  # type: ignore[method-assign]

    resultado = await escenario.barrer(BARRIDO_1)

    assert escenario.envio.llamadas == 0
    assert (escenario.fila.estado_entrega, escenario.fila.ultimo_error) == (
        EstadoEntrega.FALLIDO,
        "SIN_TELEFONO",
    )
    assert resultado.fallidos == 1


# ------------------------------------------------------------------ S2


async def test_cada_reserva_mide_su_ventana_desde_su_propio_instante() -> None:
    """Un barrido largo: la tercera reserva sale 40 minutos después del `ahora` del barrido."""
    escenario = _escenario()
    ventanas: list[tuple[datetime, datetime | None]] = []

    def avanzar_y_mirar() -> None:
        ultima = escenario.recordatorios.guardados[-1]
        ventanas.append((escenario.reloj.instante, ultima.proximo_intento_en))
        escenario.reloj.instante += timedelta(minutes=20)

    escenario.envio._al_enviar = avanzar_y_mirar
    await _tres_cobros_vencidos(escenario.cobros)
    escenario.reloj.instante = BARRIDO_1

    await escenario.barrido.ejecutar(empresa_id=EMPRESA, ahora=BARRIDO_1)

    assert [ventana for _, ventana in ventanas] == [
        BARRIDO_1 + VENTANA_DE_ENVIO,
        BARRIDO_1 + timedelta(minutes=20) + VENTANA_DE_ENVIO,
        BARRIDO_1 + timedelta(minutes=40) + VENTANA_DE_ENVIO,
    ]
    # Y lo que se registra lleva el instante del registro, no el del inicio del barrido.
    fechas = sorted(uno.enviado_en for uno in escenario.recordatorios.guardados if uno.enviado_en)
    assert fechas == [
        BARRIDO_1 + timedelta(minutes=20),
        BARRIDO_1 + timedelta(minutes=40),
        BARRIDO_1 + timedelta(minutes=60),
    ]


async def test_un_barrido_solapado_no_resuelve_incierta_una_reserva_con_ventana_vigente() -> None:
    """El barrido A reserva tarde (reloj real a +40 min de su `ahora`); el B llega a +50 min con
    el envío todavía en curso. Con la ventana medida desde el `ahora` de A ya habría vencido."""
    escenario, _ = await _con_un_cobro()
    segundo_barrido: list[ResultadoDeBarrido] = []
    mandar_de_a = escenario.envio.mandar

    async def mandar_con_un_barrido_en_medio(mensaje: MensajeListo) -> ResultadoDeEnvio:
        escenario.reloj.instante = BARRIDO_1 + timedelta(minutes=50)
        segundo_barrido.append(
            await escenario.barrido.ejecutar(
                empresa_id=EMPRESA, ahora=BARRIDO_1 + timedelta(minutes=50)
            )
        )
        return await mandar_de_a(mensaje)

    escenario.envio.mandar = mandar_con_un_barrido_en_medio  # type: ignore[method-assign]
    escenario.reloj.instante = BARRIDO_1 + timedelta(minutes=40)  # A reserva 40 minutos tarde

    await escenario.barrido.ejecutar(empresa_id=EMPRESA, ahora=BARRIDO_1)

    fila = escenario.fila
    (en_el_barrido_b,) = segundo_barrido
    assert en_el_barrido_b.fallidos == 0  # el B no la resolvió `INCIERTO`
    assert fila.ultimo_error is None
    assert fila.estado_entrega is EstadoEntrega.ENVIADO
    assert escenario.envio.llamadas == 1  # un solo envío: el de A


# ------------------------------------------------------------------ N2


class _PagaDespuesDeLaReserva(TransaccionFalsa):
    """El cobro se cancela justo después del primer commit: entre la reserva y el envío."""

    def __init__(self) -> None:
        super().__init__()
        self.cobro: Cobro | None = None

    async def confirmar(self) -> None:
        await super().confirmar()
        if self.confirmaciones == 1 and self.cobro is not None:
            self.cobro.cancelar(motivo="Cancelado a mitad del envío", ahora=BARRIDO_1)


async def test_un_cobro_cerrado_entre_la_reserva_y_el_envio_no_se_manda() -> None:
    transaccion = _PagaDespuesDeLaReserva()
    escenario = _escenario(
        transaccion=transaccion, recordatorios=RecordatoriosConBitacora(transaccion)
    )
    cobro = _cobro(vence_en_dias=0)
    await escenario.cobros.agregar(cobro)
    transaccion.cobro = cobro

    resultado = await escenario.barrer(BARRIDO_1)

    fila = escenario.fila
    assert escenario.envio.llamadas == 0
    assert fila.descartado is True
    assert (fila.ultimo_error, fila.enviado_en, fila.proximo_intento_en) == (
        COBRO_CERRADO,
        None,
        None,
    )
    assert (resultado.procesados, resultado.fallidos) == (0, 0)

    # El barrido siguiente no la resuelve `INCIERTO`: está descartada, no en curso.
    await escenario.barrer(BARRIDO_1 + VENTANA_DE_ENVIO + timedelta(hours=1))
    assert escenario.fila.ultimo_error == COBRO_CERRADO
    assert escenario.fila.ultimo_error != INCIERTO


async def test_una_falla_al_releer_el_cobro_no_manda_y_deja_la_fila_en_curso() -> None:
    escenario, cobro = await _con_un_cobro()
    originales = escenario.cobros.buscar_por_id
    llamadas = 0

    async def falla_la_segunda_lectura(cobro_id: object) -> Cobro | None:
        nonlocal llamadas
        llamadas += 1
        if llamadas == 1:
            raise DespachoNoPersistido("la base rechazó la lectura del cobro")
        return await originales(cobro_id)  # type: ignore[arg-type]

    escenario.cobros.buscar_por_id = falla_la_segunda_lectura  # type: ignore[method-assign]

    await escenario.barrer(BARRIDO_1)

    assert escenario.envio.llamadas == 0
    assert escenario.fila.intentos == 1
    assert escenario.fila.envio_en_curso is True
    assert cobro.recibe_recordatorios is True


# ------------------------------------------------------------------ N7


async def test_un_cobro_que_completo_un_reintento_no_recibe_el_paso_siguiente_en_la_corrida() -> (
    None
):
    """Paso 1 en espera de su reintento, y el paso 2 ya le toca por fechas: salen en corridas
    distintas, no las dos en la misma."""
    escenario, cobro = await _con_un_cobro(transitoria())
    await escenario.barrer(BARRIDO_1)  # paso 1: falla transitoria, queda esperando
    llegado_el_paso_2 = cobro.vence_el + timedelta(days=8)

    await escenario.barrer(llegado_el_paso_2)  # reintento del paso 1 (sale)

    assert [uno.paso for uno in escenario.recordatorios.guardados] == [1]
    assert escenario.fila.estado_entrega is EstadoEntrega.ENVIADO
    assert escenario.envio.llamadas == 2

    await escenario.barrer(llegado_el_paso_2 + timedelta(hours=1))  # la corrida siguiente: paso 2
    assert [uno.paso for uno in escenario.recordatorios.guardados] == [1, 2]
