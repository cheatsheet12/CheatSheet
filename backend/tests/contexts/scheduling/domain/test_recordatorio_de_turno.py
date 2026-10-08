"""`RecordatorioDeTurno` y `que_corresponde` (HU-E8-04, HU-E11-01; unidad `recordatorio-de-turno`).

Lo que se fija acá y un refactor podría romper sin que nada más se queje:

1. **Un recordatorio solo corresponde si el momento ya llegó y la franja ya estaba fijada** cuando
   ese momento llegó (`M >= F`): reservar un turno 3 h antes con una regla de 24 h no dispara un
   aviso tardío.
2. **Si el worker estuvo caído y corresponden varios, sale solo el más cercano** al turno; los demás
   quedan `OMITIDO`.
3. **Reintento acotado**: 3 intentos, esperas de 15 y 30 min, nunca después de la hora del turno, y
   solo para fallas transitorias.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cheatsheet.contexts.scheduling.domain.recordatorio_de_turno import (
    ANTICIPACION_SUPERADA,
    ESPERA_BASE,
    INCIERTO,
    REINTENTOS_MAXIMOS,
    TURNO_EMPEZADO,
    VENTANA_DE_ENVIO,
    PlanDeRecordatorio,
    RecordatorioDeTurno,
    ResultadoDeRecordatorio,
    que_corresponde,
)
from cheatsheet.contexts.scheduling.domain.turno import EstadoTurno, Franja, Turno
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida

H = 60  # minutos por hora

#: 15/10/2026 10:00 en la Argentina (UTC-3) = 13:00Z. La regla compara instantes UTC.
INICIO = datetime(2026, 10, 15, 13, 0, tzinfo=UTC)
RESERVADO_EL = INICIO - timedelta(days=10)


def turno(**cambios: object) -> Turno:
    base: dict[str, object] = {
        "id": uuid4(),
        "empresa_id": EmpresaId(uuid4()),
        "cliente_id": uuid4(),
        "servicio_id": uuid4(),
        "recurso_id": uuid4(),
        "franja": Franja(inicio=INICIO, duracion_min=60),
        "created_at": RESERVADO_EL,
        "franja_asignada_en": RESERVADO_EL,
    }
    base.update(cambios)
    return Turno(**base)  # type: ignore[arg-type]


def fila(uno: Turno, horas: int, **cambios: object) -> RecordatorioDeTurno:
    base: dict[str, object] = {
        "id": uuid4(),
        "empresa_id": uno.empresa_id,
        "turno_id": uno.id,
        "anticipacion_min": horas * H,
        "franja_inicio": uno.franja.inicio,
        "created_at": RESERVADO_EL,
    }
    base.update(cambios)
    return RecordatorioDeTurno(**base)  # type: ignore[arg-type]


def _resultado(uno: RecordatorioDeTurno) -> ResultadoDeRecordatorio | None:
    """Lee el resultado sin que mypy lo estreche al valor del constructor."""
    return uno.resultado


class TestQueCorresponde:
    def test_antes_del_momento_no_corresponde_nada(self) -> None:
        uno = turno()

        plan = que_corresponde(uno, [24 * H], [], INICIO - timedelta(hours=24, minutes=1))

        assert plan == PlanDeRecordatorio()

    def test_desde_el_momento_exacto_corresponde(self) -> None:
        """Caso 12: 15/10 10:00 AR (13:00Z) corresponde desde el 14/10 13:00Z con 24 h."""
        uno = turno()

        plan = que_corresponde(uno, [24 * H], [], datetime(2026, 10, 14, 13, 0, tzinfo=UTC))

        assert plan.enviar == 24 * H

    def test_un_turno_que_ya_empezo_no_recibe_nada(self) -> None:
        uno = turno()

        assert que_corresponde(uno, [24 * H], [], INICIO) == PlanDeRecordatorio()

    def test_reservado_dentro_de_la_ventana_no_se_recuerda(self) -> None:
        """Caso 10: reservado 3 h antes con regla de 24 h, el momento ya era pasado al reservar."""
        reservado = INICIO - timedelta(hours=3)
        uno = turno(created_at=reservado, franja_asignada_en=reservado)

        plan = que_corresponde(uno, [24 * H], [], INICIO - timedelta(hours=2))

        assert plan == PlanDeRecordatorio()

    def test_confirmado_dentro_de_la_ventana_si_se_recuerda(self) -> None:
        """Caso 11: lo que cuenta es cuándo se fijó la franja, no cuándo se confirmó."""
        uno = turno(
            estado=EstadoTurno.CONFIRMADO,
            updated_at=INICIO - timedelta(hours=2),
        )

        plan = que_corresponde(uno, [24 * H], [], INICIO - timedelta(hours=2))

        assert plan.enviar == 24 * H

    def test_un_turno_reprogramado_dentro_de_la_ventana_no_se_recuerda(self) -> None:
        uno = turno()
        movido_en = INICIO - timedelta(hours=5)
        uno.reprogramar(Franja(inicio=INICIO, duracion_min=60), 0, movido_en)

        assert que_corresponde(uno, [24 * H], [], movido_en) == PlanDeRecordatorio()

    def test_con_varias_corresponde_solo_la_mas_cercana_y_las_otras_se_omiten(self) -> None:
        """Caso 9: 48 h y 24 h, el worker caído hasta faltar 20 h."""
        uno = turno()

        plan = que_corresponde(uno, [48 * H, 24 * H], [], INICIO - timedelta(hours=20))

        assert plan == PlanDeRecordatorio(enviar=24 * H, omitir=(48 * H,))

    def test_una_anticipacion_con_fila_no_se_repite(self) -> None:
        uno = turno()
        previa = fila(uno, 24, resultado=ResultadoDeRecordatorio.ENVIADO)

        plan = que_corresponde(uno, [24 * H], [previa], INICIO - timedelta(hours=10))

        assert plan == PlanDeRecordatorio()

    def test_si_la_mas_cercana_ya_se_resolvio_la_mas_lejana_se_omite(self) -> None:
        """Con 24 h enviado, que la regla gane una de 48 h no manda un aviso «más viejo» después."""
        uno = turno()
        previa = fila(uno, 24, resultado=ResultadoDeRecordatorio.ENVIADO)

        plan = que_corresponde(uno, [48 * H, 24 * H], [previa], INICIO - timedelta(hours=10))

        assert plan == PlanDeRecordatorio(omitir=(48 * H,))

    def test_con_una_mas_cercana_resuelta_en_cualquier_estado_las_mas_viejas_se_omiten(
        self,
    ) -> None:
        """D-U8-3: la regla no depende de cómo terminó la más cercana, solo de que exista."""
        uno = turno()
        for resultado in ResultadoDeRecordatorio:
            previa = fila(uno, 12, resultado=resultado)

            plan = que_corresponde(uno, [24 * H, 12 * H], [previa], INICIO - timedelta(hours=5))

            assert plan == PlanDeRecordatorio(omitir=(24 * H,)), resultado

    def test_con_una_mas_cercana_en_curso_o_esperando_reintento_las_mas_viejas_se_omiten(
        self,
    ) -> None:
        """D-U8-3: una fila sin `resultado` (en vuelo o con reintento) también supera a las viejas.

        Si no, el barrido mandaría el aviso de 24 h mientras el de 12 h espera su reintento.
        """
        uno = turno()
        en_vuelo = fila(uno, 12, intentos=1, proximo_intento_en=INICIO - timedelta(hours=4))
        esperando = fila(
            uno,
            12,
            intentos=1,
            proximo_intento_en=INICIO - timedelta(hours=4),
            ultimo_error="MENSAJERIA_SATURADA",
        )
        assert en_vuelo.resultado is None
        assert esperando.resultado is None

        for previa in (en_vuelo, esperando):
            plan = que_corresponde(uno, [24 * H, 12 * H], [previa], INICIO - timedelta(hours=5))

            assert plan == PlanDeRecordatorio(omitir=(24 * H,))

    def test_una_franja_fijada_despues_del_momento_omite_esa_anticipacion(self) -> None:
        """D-U8-4: los turnos existentes al migrar toman la fecha del deploy como `F`.

        Con el deploy 20 h antes del turno, la de 24 h ya llegaba tarde (`M < F`) y no sale;
        la de 12 h sí, porque su momento es posterior al deploy.
        """
        deploy = INICIO - timedelta(hours=20)
        uno = turno(created_at=RESERVADO_EL, franja_asignada_en=deploy)

        plan = que_corresponde(uno, [24 * H], [], deploy + timedelta(minutes=1))
        assert plan == PlanDeRecordatorio()

        plan = que_corresponde(uno, [24 * H, 12 * H], [], INICIO - timedelta(hours=11))
        assert plan == PlanDeRecordatorio(enviar=12 * H)

    def test_las_filas_de_otra_franja_no_cuentan(self) -> None:
        """Reprogramar genera claves nuevas: la fila de la franja vieja no frena la nueva."""
        uno = turno()
        vieja = fila(
            uno,
            24,
            franja_inicio=INICIO - timedelta(days=1),
            resultado=ResultadoDeRecordatorio.ENVIADO,
        )

        plan = que_corresponde(uno, [24 * H], [vieja], INICIO - timedelta(hours=10))

        assert plan.enviar == 24 * H

    @pytest.mark.parametrize(
        "estado", [EstadoTurno.CANCELADO, EstadoTurno.COMPLETADO, EstadoTurno.NO_SHOW]
    )
    def test_un_turno_cerrado_no_recibe_nada(self, estado: EstadoTurno) -> None:
        uno = turno(estado=estado)

        assert que_corresponde(uno, [24 * H], [], INICIO - timedelta(hours=10)) == (
            PlanDeRecordatorio()
        )

    def test_sin_anticipaciones_no_hay_nada_que_mandar(self) -> None:
        assert que_corresponde(turno(), [], [], INICIO - timedelta(hours=10)) == (
            PlanDeRecordatorio()
        )


class TestEntidad:
    def test_la_anticipacion_tiene_limites(self) -> None:
        uno = turno()
        with pytest.raises(EntradaInvalida):
            fila(uno, 0)
        with pytest.raises(EntradaInvalida):
            fila(uno, 169)

    def test_el_momento_es_el_inicio_menos_la_anticipacion(self) -> None:
        uno = turno()

        assert fila(uno, 24).momento == INICIO - timedelta(hours=24)

    def test_iniciar_intento_cuenta_y_abre_la_ventana(self) -> None:
        ahora = INICIO - timedelta(hours=24)
        uno = fila(turno(), 24)

        uno.iniciar_intento(ahora)

        assert uno.intentos == 1
        assert uno.proximo_intento_en == ahora + VENTANA_DE_ENVIO
        assert uno.envio_en_curso
        assert not uno.esperando_reintento
        assert not uno.envio_perdido(ahora)
        assert uno.envio_perdido(ahora + VENTANA_DE_ENVIO)

    def test_transitoria_espera_15_y_30_minutos_y_la_tercera_agota(self) -> None:
        """Caso 13."""
        ahora = INICIO - timedelta(hours=24)
        uno = fila(turno(), 24)

        uno.iniciar_intento(ahora)
        assert uno.registrar_falla(ahora, codigo="131056", transitoria=True)
        assert uno.proximo_intento_en == ahora + ESPERA_BASE
        assert uno.esperando_reintento
        assert uno.ultimo_error == "131056"
        assert uno.reintento_vencido(ahora + ESPERA_BASE)
        assert not uno.reintento_vencido(ahora)

        uno.iniciar_intento(ahora)
        assert uno.registrar_falla(ahora, codigo="131056", transitoria=True)
        assert uno.proximo_intento_en == ahora + 2 * ESPERA_BASE

        uno.iniciar_intento(ahora)
        assert uno.intentos == REINTENTOS_MAXIMOS
        assert not uno.registrar_falla(ahora, codigo="131056", transitoria=True)
        assert _resultado(uno) is ResultadoDeRecordatorio.FALLIDO
        assert uno.procesado_en == ahora

    @pytest.mark.parametrize("codigo", ["131047", "INCIERTO", "ERROR_PROPIO"])
    def test_permanente_o_incierta_falla_sin_reintento(self, codigo: str) -> None:
        ahora = INICIO - timedelta(hours=24)
        uno = fila(turno(), 24)
        uno.iniciar_intento(ahora)

        assert not uno.registrar_falla(ahora, codigo=codigo, transitoria=False)

        assert _resultado(uno) is ResultadoDeRecordatorio.FALLIDO
        assert uno.ultimo_error == codigo
        assert uno.intentos == 1

    def test_una_espera_que_cae_despues_del_turno_descarta(self) -> None:
        """Caso 13: nunca se manda un recordatorio después de la hora del turno."""
        ahora = INICIO - timedelta(minutes=10)
        uno = fila(turno(), 24)
        uno.iniciar_intento(ahora)

        assert not uno.registrar_falla(ahora, codigo="131056", transitoria=True)

        assert _resultado(uno) is ResultadoDeRecordatorio.DESCARTADO
        assert uno.ultimo_error == TURNO_EMPEZADO

    def test_marcar_enviado_cierra_y_limpia_el_error(self) -> None:
        ahora = INICIO - timedelta(hours=24)
        uno = fila(turno(), 24)
        uno.iniciar_intento(ahora)
        uno.registrar_falla(ahora, codigo="131056", transitoria=True)
        uno.iniciar_intento(ahora)

        uno.marcar_enviado(ahora)

        assert _resultado(uno) is ResultadoDeRecordatorio.ENVIADO
        assert uno.ultimo_error is None
        assert uno.proximo_intento_en is None
        assert uno.terminado

    def test_un_envio_perdido_se_resuelve_como_incierto(self) -> None:
        ahora = INICIO - timedelta(hours=24)
        uno = fila(turno(), 24)
        uno.iniciar_intento(ahora)

        uno.fallar(ahora + VENTANA_DE_ENVIO, INCIERTO)

        assert _resultado(uno) is ResultadoDeRecordatorio.FALLIDO
        assert uno.ultimo_error == INCIERTO
        assert not uno.envio_en_curso

    def test_omitir_y_descartar_guardan_el_motivo_y_cierran(self) -> None:
        ahora = INICIO - timedelta(hours=24)
        omitida = fila(turno(), 48)
        omitida.omitir(ahora, ANTICIPACION_SUPERADA)
        descartada = fila(turno(), 24)
        descartada.descartar(ahora, TURNO_EMPEZADO)

        assert _resultado(omitida) is ResultadoDeRecordatorio.OMITIDO
        assert omitida.ultimo_error == ANTICIPACION_SUPERADA
        assert _resultado(descartada) is ResultadoDeRecordatorio.DESCARTADO
        assert descartada.procesado_en == ahora

    def test_el_motivo_se_corta_al_largo_de_la_columna(self) -> None:
        uno = fila(turno(), 24)

        uno.fallar(INICIO, "x" * 200)

        assert uno.ultimo_error is not None
        assert len(uno.ultimo_error) == 60

    def test_para_ata_la_fila_a_la_franja_del_turno(self) -> None:
        origen = turno()

        uno = RecordatorioDeTurno.para(
            id=uuid4(), turno=origen, anticipacion_min=24 * H, ahora=RESERVADO_EL
        )

        assert uno.turno_id == origen.id
        assert uno.empresa_id == origen.empresa_id
        assert uno.franja_inicio == INICIO
        assert uno.resultado is None
        assert uno.intentos == 0
