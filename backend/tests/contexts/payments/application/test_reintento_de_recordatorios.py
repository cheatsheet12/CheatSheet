"""El barrido de recordatorios reintenta lo transitorio y nunca lo incierto (U7, tramo ii, D-U7-3).

Casos 15 a 20 y 22 del plan, más el orden que cierra el hallazgo H1: **la fila se confirma
antes de hablar con Meta y el resultado después**, sin ninguna llamada a Meta con la transacción
abierta. Un callback `failed` o `delivered` que llegue después del envío encuentra la fila.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from cheatsheet.contexts.payments.domain.recordatorio import (
    COBRO_CERRADO,
    INCIERTO,
    REINTENTOS_MAXIMOS,
    VENTANA_DE_ENVIO,
    EstadoEntrega,
    Recordatorio,
)
from cheatsheet.shared.auditoria import EventoAuditable, Resultado
from cheatsheet.shared.transaccion import DespachoNoPersistido

from tests.contexts.payments.application.dobles_de_reintento import (
    BARRIDO_1,
    RecordatoriosConBitacora,
    _con_un_cobro,
    _escenario,
    enviado,
    incierto,
    permanente,
    transitoria,
)
from tests.contexts.payments.application.test_cobros_y_recordatorios import (
    TransaccionFalsa,
    _cobro,
    _tres_cobros_vencidos,
)

pytestmark = pytest.mark.asyncio

# ------------------------------------------------------------------ H1: el orden


async def test_la_fila_se_confirma_antes_de_hablar_con_meta_y_el_resultado_despues() -> None:
    escenario, _ = await _con_un_cobro(enviado("wamid-1"))

    await escenario.barrer(BARRIDO_1)

    assert escenario.fila.externo_id == "wamid-1"
    assert escenario.transaccion.bitacora == [
        "preparar",
        "agregar",
        "confirmar",
        "enviar",
        "guardar",
        "confirmar",
    ]


async def test_en_el_momento_del_envio_la_fila_ya_esta_registrada_como_en_curso() -> None:
    """Es lo que ve un callback que llegue antes de que el barrido termine: la fila existe."""
    vistas: list[tuple[int, datetime | None, str | None, datetime | None]] = []
    transaccion = TransaccionFalsa()
    recordatorios = RecordatoriosConBitacora(transaccion)

    def mirar() -> None:
        (fila,) = recordatorios.guardados
        vistas.append((fila.intentos, fila.proximo_intento_en, fila.ultimo_error, fila.enviado_en))

    escenario = _escenario(recordatorios=recordatorios, transaccion=transaccion)
    escenario.envio._al_enviar = mirar
    await escenario.cobros.agregar(_cobro(vence_en_dias=0))

    await escenario.barrer(BARRIDO_1)

    assert vistas == [(1, BARRIDO_1 + VENTANA_DE_ENVIO, None, None)]


async def test_ningun_recordatorio_habla_con_meta_con_la_transaccion_abierta() -> None:
    escenario = _escenario(transitoria(), enviado(), permanente())
    await _tres_cobros_vencidos(escenario.cobros)

    await escenario.barrer(BARRIDO_1)

    assert escenario.envio.llamadas == 3
    assert escenario.envio.con_transaccion_abierta is False


# ------------------------------------------------------------------ casos 15 y 16


async def test_una_falla_transitoria_deja_la_misma_fila_esperando_una_hora() -> None:
    """Caso 15: `intentos=1`, `proximo_intento_en=+1 h`, sin `INSERT` nuevo."""
    escenario, _ = await _con_un_cobro(transitoria("131056"))

    resultado = await escenario.barrer(BARRIDO_1)

    fila = escenario.fila
    assert fila.enviado_en is None
    assert fila.estado_entrega is None
    assert (fila.intentos, fila.ultimo_error) == (1, "131056")
    assert fila.proximo_intento_en == BARRIDO_1 + timedelta(hours=1)
    assert (resultado.procesados, resultado.fallidos, resultado.reintentos) == (0, 0, 1)


async def test_no_reintenta_antes_de_la_espera_y_si_despues_sobre_la_misma_fila() -> None:
    """Caso 16: antes de `proximo_intento_en` no manda; después, `UPDATE` y sale con su `wamid`."""
    escenario, _ = await _con_un_cobro(transitoria(), enviado("wamid-2"))
    await escenario.barrer(BARRIDO_1)
    id_de_la_fila = escenario.fila.id

    await escenario.barrer(BARRIDO_1 + timedelta(minutes=59))
    assert escenario.envio.llamadas == 1

    resultado = await escenario.barrer(BARRIDO_1 + timedelta(hours=1))

    fila = escenario.fila  # una sola fila: ningún `INSERT` nuevo
    assert escenario.envio.llamadas == 2
    assert fila.id == id_de_la_fila
    assert (fila.intentos, fila.externo_id) == (2, "wamid-2")
    assert fila.estado_entrega is EstadoEntrega.ENVIADO
    assert fila.enviado_en == BARRIDO_1 + timedelta(hours=1)
    assert fila.ultimo_error is None
    assert resultado.procesados == 1


# ------------------------------------------------------------------ caso 17


async def test_el_tercer_intento_transitorio_deja_fallido_y_la_cadena_sigue() -> None:
    """Caso 17: `FALLIDO` con `enviado_en` puesto; el barrido siguiente evalúa el paso 2."""
    escenario, cobro = await _con_un_cobro(*[transitoria() for _ in range(REINTENTOS_MAXIMOS)])
    ahora = BARRIDO_1
    for horas in (0, 1, 3):
        ahora = BARRIDO_1 + timedelta(hours=horas)
        resultado = await escenario.barrer(ahora)

    fila = escenario.fila
    assert escenario.envio.llamadas == REINTENTOS_MAXIMOS
    assert fila.estado_entrega is EstadoEntrega.FALLIDO
    assert fila.enviado_en == ahora
    assert fila.intentos == REINTENTOS_MAXIMOS
    assert fila.proximo_intento_en is None
    assert (resultado.procesados, resultado.fallidos) == (0, 1)

    # A los 8 días del vencimiento le toca el paso 2: la cadena no se detuvo.
    await escenario.barrer(cobro.vence_el + timedelta(days=8))
    assert [uno.paso for uno in escenario.recordatorios.guardados] == [1, 2]


async def test_la_espera_entre_intentos_es_de_una_hora_y_luego_de_dos() -> None:
    escenario, _ = await _con_un_cobro(transitoria(), transitoria(), transitoria())
    esperas: list[datetime | None] = []

    for horas in (0, 1):
        await escenario.barrer(BARRIDO_1 + timedelta(hours=horas))
        esperas.append(escenario.fila.proximo_intento_en)

    assert esperas == [BARRIDO_1 + timedelta(hours=1), BARRIDO_1 + timedelta(hours=3)]


async def test_el_evento_de_bitacora_se_publica_una_vez_y_al_final() -> None:
    """Un intento intermedio no es una falla de la bitácora: solo el último lo es."""
    escenario, _ = await _con_un_cobro(*[transitoria() for _ in range(REINTENTOS_MAXIMOS)])

    for horas in (0, 1, 3):
        await escenario.barrer(BARRIDO_1 + timedelta(hours=horas))
        publicados = [
            e.resultado
            for e in escenario.publicador.eventos
            if isinstance(e, EventoAuditable) and e.accion == "enviar_recordatorio"
        ]
        assert publicados == ([] if horas < 3 else [Resultado.ERROR])


# ------------------------------------------------------------------ casos 18 y 19


async def test_un_resultado_incierto_se_registra_fallido_y_nunca_se_reintenta() -> None:
    """Caso 18: timeout de lectura. Meta pudo haberlo aceptado y no hay clave de idempotencia."""
    escenario, _ = await _con_un_cobro(incierto())

    await escenario.barrer(BARRIDO_1)
    await escenario.barrer(BARRIDO_1 + timedelta(days=1))

    fila = escenario.fila
    assert escenario.envio.llamadas == 1
    assert (fila.estado_entrega, fila.ultimo_error) == (EstadoEntrega.FALLIDO, INCIERTO)
    assert fila.intentos == 1


async def test_un_rechazo_permanente_falla_una_vez_sin_reintento() -> None:
    """Caso 19: 400 131026."""
    escenario, _ = await _con_un_cobro(permanente("131026"))

    resultado = await escenario.barrer(BARRIDO_1)
    await escenario.barrer(BARRIDO_1 + timedelta(days=1))

    fila = escenario.fila
    assert escenario.envio.llamadas == 1
    assert (fila.estado_entrega, fila.ultimo_error) == (EstadoEntrega.FALLIDO, "131026")
    assert (resultado.fallidos, resultado.reintentos) == (1, 0)


async def test_un_adaptador_que_levanta_no_se_reintenta() -> None:
    escenario, _ = await _con_un_cobro(RuntimeError("rompió el contrato"))

    await escenario.barrer(BARRIDO_1)
    await escenario.barrer(BARRIDO_1 + timedelta(days=1))

    assert escenario.envio.llamadas == 1
    assert escenario.fila.ultimo_error == "ERROR"


# ------------------------------------------------------------------ caso 20


async def test_un_cobro_cerrado_mientras_esperaba_descarta_la_fila_sin_enviar() -> None:
    """Caso 20: `COBRO_CERRADO`, ningún envío."""
    escenario, cobro = await _con_un_cobro(transitoria())
    await escenario.barrer(BARRIDO_1)
    cobro.cancelar(motivo="Cancelado antes del reintento", ahora=BARRIDO_1)

    await escenario.barrer(BARRIDO_1 + timedelta(hours=1))

    fila = escenario.fila
    assert escenario.envio.llamadas == 1
    assert fila.descartado is True
    assert fila.ultimo_error == COBRO_CERRADO
    assert fila.enviado_en is None
    assert fila.proximo_intento_en is None


# ------------------------------------------------------------------ caso 22


async def test_el_reintento_de_un_cobro_no_voltea_a_los_demas() -> None:
    """Caso 22: cada ítem corre en su propio savepoint; un fallo de uno no toca a los otros."""

    class NoGuardaElSegundo(RecordatoriosConBitacora):
        async def guardar(self, recordatorio: Recordatorio) -> None:
            if len(self.guardados) > 1 and recordatorio.id == self.guardados[1].id:
                raise DespachoNoPersistido("la base rechazó el guardado")
            await super().guardar(recordatorio)

    transaccion = TransaccionFalsa()
    escenario = _escenario(
        *[transitoria() for _ in range(4)],
        recordatorios=NoGuardaElSegundo(transaccion),
        transaccion=transaccion,
    )
    await _tres_cobros_vencidos(escenario.cobros)
    await escenario.barrer(BARRIDO_1)
    primero, segundo, tercero = escenario.recordatorios.guardados
    assert (primero.intentos, segundo.intentos, tercero.intentos) == (1, 1, 1)
    # El segundo quedó «en curso» (su resultado no se guardó): la base no vio la espera.
    assert (segundo.ultimo_error, segundo.proximo_intento_en) == (
        None,
        BARRIDO_1 + VENTANA_DE_ENVIO,
    )

    await escenario.barrer(BARRIDO_1 + timedelta(hours=1))
    primero, segundo, tercero = escenario.recordatorios.guardados

    # Los dos que se guardaron esperaron y se reintentaron; el otro quedó «en curso» y, vencida su
    # ventana, se resolvió incierto sin un envío más: 3 primeros intentos + 2 reintentos.
    assert escenario.envio.llamadas == 5
    assert (primero.intentos, tercero.intentos) == (2, 2)
    assert segundo.intentos == 1
