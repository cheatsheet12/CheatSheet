"""El envío de un recordatorio de turno en tres tiempos y su reintento (D-U8-8, D-U8-10).

Lo que se fija acá (casos 19, 22 a 24, 26):

1. **Orden**: se prepara y se reserva, se confirma, **recién entonces** se habla con el canal, y el
   resultado se registra y confirma después. Al llamar al canal no hay nada sin confirmar.
2. **Reintento acotado**: solo la falla transitoria, 3 intentos, esperas de 15 y 30 min, sobre la misma
   fila y nunca después de la hora del turno. Incierta o permanente: `FALLIDO`, sin reenvío.
3. **Caídas**: un envío en curso con la ventana vencida se resuelve `INCIERTO` y **nunca** se reenvía.
4. Lo que la base rechaza deshace solo ese ítem, no el barrido.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from cheatsheet.contexts.scheduling.application.ports_de_recordatorios import (
    RecordatorioListo,
    ResultadoDelEnvio,
    SinTelefono,
)
from cheatsheet.contexts.scheduling.domain.recordatorio_de_turno import (
    ESPERA_BASE,
    REINTENTOS_MAXIMOS,
    VENTANA_DE_ENVIO,
    RecordatorioDeTurno,
    ResultadoDeRecordatorio,
)
from cheatsheet.contexts.scheduling.domain.turno import Turno
from cheatsheet.shared.auditoria import EventoAuditable, Resultado
from cheatsheet.shared.transaccion import DespachoNoPersistido

from tests.contexts.scheduling.application.dobles_de_recordatorios import (
    INICIO,
    VENTANA_DE_24H,
    AgendaFalsa,
    cancelado,
    escenario,
    incierto,
    permanente,
    transitoria,
    turno,
)

pytestmark = pytest.mark.asyncio

QUINCE_MIN = timedelta(minutes=15)


class TestLosTresTiempos:
    async def test_la_fila_se_confirma_antes_de_hablar_con_el_canal(self) -> None:
        """**Caso 25 (versión de unidad).** Sin escrituras sin confirmar al llamar al canal."""
        e = escenario()
        e.turnos.agregar(turno())

        await e.barrer()

        assert e.envio.con_transaccion_abierta is False
        assert e.transaccion.bitacora == [
            "preparar",
            "agregar",
            "confirmar",  # tiempo 1: reservar y confirmar
            "enviar",  # tiempo 2: mandar
            "guardar",
            "confirmar",  # tiempo 3: registrar y confirmar
        ]
        assert e.transaccion.confirmaciones == 2

    async def test_la_fila_queda_en_curso_con_la_ventana_abierta_mientras_el_canal_responde(
        self,
    ) -> None:
        e = escenario()
        e.turnos.agregar(turno())
        vista: list[tuple[int, object]] = []
        e.envio._al_enviar = lambda: vista.append((e.fila.intentos, e.fila.proximo_intento_en))

        await e.barrer()

        assert vista == [(1, VENTANA_DE_24H + VENTANA_DE_ENVIO)]

    async def test_lo_que_se_escribe_sale_del_reloj_real_y_no_del_del_barrido(self) -> None:
        """S2 de U7: la ventana y el cierre se miden al escribir."""
        e = escenario()
        e.turnos.agregar(turno())
        ahora_del_barrido = VENTANA_DE_24H
        e.envio._al_enviar = lambda: setattr(
            e.reloj, "instante", ahora_del_barrido + timedelta(minutes=7)
        )

        await e.barrer(ahora_del_barrido)

        assert e.fila.procesado_en == ahora_del_barrido + timedelta(minutes=7)

    async def test_la_bitacora_registra_un_solo_evento_sin_datos_personales(self) -> None:
        e = escenario()
        uno = turno()
        e.turnos.agregar(uno)

        await e.barrer()

        (evento,) = e.publicador.eventos
        assert isinstance(evento, EventoAuditable)
        assert (evento.accion, evento.resultado, evento.usuario_id) == (
            "enviar_recordatorio_de_turno",
            Resultado.COMPLETADO,
            None,
        )
        assert evento.entidad_afectada == f"Turno:{uno.id}"
        assert evento.detalle == {"desenlace": "ENVIADO"}  # distinguible de un descarte

    async def test_cancelado_entre_reservar_y_mandar_se_descarta_sin_llamar_al_canal(self) -> None:
        """**Caso 19.**"""
        e = escenario()
        uno = turno()
        e.turnos.agregar(uno)
        # El preparar es lo último antes de confirmar la reserva: ahí alguien cancela el turno.
        e.envio._al_enviar = lambda: None
        original = e.envio.preparar

        async def preparar_y_cancelar(
            turno_a_preparar: Turno, anticipacion: int
        ) -> RecordatorioListo | SinTelefono:
            listo = await original(turno_a_preparar, anticipacion)
            e.turnos.agregar(cancelado(uno))
            return listo

        e.envio.preparar = preparar_y_cancelar  # type: ignore[method-assign, assignment]  # el doble sustituye el método

        resultado = await e.barrer()

        assert resultado.descartados == 1
        assert e.envio.enviados == []
        assert e.fila.resultado is ResultadoDeRecordatorio.DESCARTADO
        assert e.fila.ultimo_error == "TURNO_CERRADO"
        (evento,) = e.publicador.eventos  # el descarte deja su evento de bitácora
        assert isinstance(evento, EventoAuditable)
        assert evento.detalle == {"desenlace": "DESCARTADO", "motivo": "TURNO_CERRADO"}


class TestElReintento:
    async def test_una_falla_transitoria_espera_15_minutos_y_reintenta_sobre_la_misma_fila(
        self,
    ) -> None:
        """**Caso 22.**"""
        e = escenario(transitoria())
        e.turnos.agregar(turno())

        primero = await e.barrer()

        assert primero.en_reintento == 1
        fila_id = e.fila.id
        assert e.fila.resultado is None
        assert e.fila.proximo_intento_en == VENTANA_DE_24H + ESPERA_BASE
        assert e.fila.ultimo_error == "SATURADA"
        assert e.publicador.eventos == []  # un intento intermedio no es una falla de la bitácora

        segundo = await e.barrer(VENTANA_DE_24H + ESPERA_BASE)

        assert segundo.enviados == 1
        assert e.fila.id == fila_id  # un UPDATE, nunca un INSERT
        assert len(e.recordatorios.filas) == 1
        assert e.fila.intentos == 2
        assert e.fila.resultado is ResultadoDeRecordatorio.ENVIADO

    async def test_sin_cumplirse_la_espera_no_se_reintenta(self) -> None:
        e = escenario(transitoria())
        e.turnos.agregar(turno())
        await e.barrer()

        resultado = await e.barrer(VENTANA_DE_24H + ESPERA_BASE - timedelta(minutes=1))

        assert not resultado.hubo_actividad
        assert len(e.envio.enviados) == 1

    async def test_agotados_los_intentos_queda_fallido_con_esperas_de_15_y_30_minutos(self) -> None:
        e = escenario(transitoria(), transitoria(), transitoria())
        e.turnos.agregar(turno())
        instante = VENTANA_DE_24H
        esperas: list[timedelta] = []

        for _ in range(REINTENTOS_MAXIMOS):
            await e.barrer(instante)
            if e.fila.proximo_intento_en is None:
                break
            esperas.append(e.fila.proximo_intento_en - instante)
            instante = e.fila.proximo_intento_en

        assert esperas == [QUINCE_MIN, 2 * QUINCE_MIN]
        assert e.fila.resultado is ResultadoDeRecordatorio.FALLIDO
        assert e.fila.intentos == REINTENTOS_MAXIMOS
        assert len(e.envio.enviados) == REINTENTOS_MAXIMOS
        (evento,) = e.publicador.eventos
        assert isinstance(evento, EventoAuditable)
        assert evento.resultado is Resultado.ERROR

    @pytest.mark.parametrize("resultado", [incierto(), permanente("131047")])
    async def test_incierto_o_permanente_queda_fallido_sin_reintento(
        self, resultado: ResultadoDelEnvio
    ) -> None:
        """**Caso 23.** Timeout de lectura (INCIERTO) y 131047: no se reenvían."""
        e = escenario(resultado)
        e.turnos.agregar(turno())

        primero = await e.barrer()
        segundo = await e.barrer(VENTANA_DE_24H + timedelta(hours=1))

        assert primero.fallidos == 1
        assert not segundo.hubo_actividad
        assert e.fila.resultado is ResultadoDeRecordatorio.FALLIDO
        assert e.fila.ultimo_error == resultado.falla
        assert len(e.envio.enviados) == 1

    async def test_un_adaptador_que_levanta_deja_el_recordatorio_fallido_sin_reintento(
        self,
    ) -> None:
        e = escenario(RuntimeError("falló con 5491112345678"))
        e.turnos.agregar(turno())

        resultado = await e.barrer()

        assert resultado.fallidos == 1
        assert e.fila.ultimo_error == "ERROR"

    async def test_la_espera_que_cae_despues_del_turno_lo_descarta(self) -> None:
        """Nunca después de la hora del turno: sin tiempo para el reintento → `TURNO_EMPEZADO`."""
        e = escenario(transitoria())
        e.turnos.agregar(turno())

        resultado = await e.barrer(INICIO - timedelta(minutes=10))

        assert resultado.descartados == 1
        assert e.fila.resultado is ResultadoDeRecordatorio.DESCARTADO
        assert e.fila.ultimo_error == "TURNO_EMPEZADO"
        (evento,) = e.publicador.eventos  # el descarte deja su evento de bitácora
        assert isinstance(evento, EventoAuditable)
        assert evento.detalle == {"desenlace": "DESCARTADO", "motivo": "TURNO_EMPEZADO"}

    async def test_cancelado_con_un_reintento_pendiente_se_descarta(self) -> None:
        """**Caso 19.** `TURNO_CERRADO`, sin llamar al canal."""
        e = escenario(transitoria())
        uno = turno()
        e.turnos.agregar(uno)
        await e.barrer()
        e.turnos.agregar(cancelado(uno))

        resultado = await e.barrer(VENTANA_DE_24H + ESPERA_BASE)

        assert resultado.descartados == 1
        assert e.fila.ultimo_error == "TURNO_CERRADO"
        assert len(e.envio.enviados) == 1

    async def test_con_la_agenda_apagada_no_se_reintenta(self) -> None:
        e = escenario(transitoria())
        e.turnos.agregar(turno())
        await e.barrer()
        e.barrido._agenda = AgendaFalsa(apagada=True)

        resultado = await e.barrer(VENTANA_DE_24H + ESPERA_BASE)

        assert resultado.descartados == 1
        assert e.fila.ultimo_error == "AGENDA_APAGADA"
        assert len(e.envio.enviados) == 1


class TestLasCaidas:
    async def test_un_envio_en_curso_con_la_ventana_vencida_queda_incierto_y_no_se_reenvia(
        self,
    ) -> None:
        """**Caso 24.** El proceso murió después de reservar: Meta pudo haberlo aceptado."""
        e = escenario(RuntimeError("murió"))
        e.turnos.agregar(turno())
        e.recordatorios.fallar_al_guardar = lambda _: True  # el resultado nunca se registró
        await e.barrer()
        e.recordatorios.fallar_al_guardar = None
        assert e.fila.envio_en_curso  # sin resultado, con la ventana abierta

        resultado = await e.barrer(VENTANA_DE_24H + VENTANA_DE_ENVIO + timedelta(minutes=1))

        assert resultado.fallidos == 1
        assert e.fila.resultado is ResultadoDeRecordatorio.FALLIDO
        assert e.fila.ultimo_error == "INCIERTO"
        assert len(e.envio.enviados) == 1  # nunca se reenvía
        (evento,) = e.publicador.eventos
        assert isinstance(evento, EventoAuditable)
        assert evento.resultado is Resultado.ERROR

    async def test_con_la_ventana_abierta_la_fila_en_curso_no_se_toca(self) -> None:
        """Un barrido solapado no da por perdida una reserva cuya ventana todavía corre."""
        e = escenario()
        e.turnos.agregar(turno())
        e.recordatorios.fallar_al_guardar = lambda _: True
        await e.barrer()
        e.recordatorios.fallar_al_guardar = None

        resultado = await e.barrer(VENTANA_DE_24H + timedelta(minutes=10))

        assert not resultado.hubo_actividad
        assert e.fila.resultado is None
        assert len(e.envio.enviados) == 1

    async def test_si_la_reserva_no_se_confirma_nada_sale(self) -> None:
        e = escenario()
        e.turnos.agregar(turno())
        e.transaccion.fallar_la_confirmacion_numero = 1

        resultado = await e.barrer()

        assert not resultado.hubo_actividad
        assert e.envio.enviados == []


class TestLoQueLaBaseRechaza:
    async def test_un_despacho_no_persistido_no_voltea_los_demas_turnos_del_barrido(self) -> None:
        """**Caso 26.**"""
        e = escenario()
        primero, segundo = turno(), turno()
        e.turnos.agregar(primero)
        e.turnos.agregar(segundo)
        original = e.recordatorios.agregar
        llamadas = 0

        async def agregar_con_un_rechazo(recordatorio: RecordatorioDeTurno) -> None:
            nonlocal llamadas
            llamadas += 1
            if llamadas == 1:
                raise DespachoNoPersistido("la base rechazó el despacho")
            await original(recordatorio)

        e.recordatorios.agregar = agregar_con_un_rechazo  # type: ignore[method-assign]  # el doble simula el rechazo

        resultado = await e.barrer()

        assert resultado.enviados == 1
        assert len(e.envio.enviados) == 1
        assert e.aislamiento.deshechos == 1

    async def test_si_el_resultado_no_se_registra_la_fila_queda_en_curso_y_no_se_reenvia(
        self,
    ) -> None:
        e = escenario()
        e.turnos.agregar(turno())
        e.recordatorios.fallar_al_guardar = lambda _: True

        resultado = await e.barrer()
        e.recordatorios.fallar_al_guardar = None
        despues = await e.barrer(VENTANA_DE_24H + VENTANA_DE_ENVIO + timedelta(minutes=1))

        assert not resultado.hubo_actividad
        assert despues.fallidos == 1
        assert len(e.envio.enviados) == 1
        assert e.fila.ultimo_error == "INCIERTO"

    async def test_dos_barridos_solapados_sobre_la_misma_clave_mandan_una_sola_vez(self) -> None:
        """La clave única cubre al que llega segundo (versión de unidad del caso 30)."""
        e = escenario()
        e.turnos.agregar(turno())
        # El segundo barrido leyó los turnos antes de que el primero escribiera: no vio la fila.
        turnos_vistos = await e.turnos.abiertos_con_inicio_entre(VENTANA_DE_24H, INICIO)
        await e.barrer()
        resultado = await e.barrido._envio.enviar_nuevo(
            turno=turnos_vistos[0], anticipacion_min=24 * 60
        )

        assert resultado.value == "NADA"
        assert len(e.envio.enviados) == 1
        assert len(e.recordatorios.filas) == 1
