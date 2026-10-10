"""`Turno` — la máquina de estados y la franja (HU-E7-01 … HU-E7-03).

Tres afirmaciones de las historias se fijan acá, y las tres son cosas que un refactor podría
romper sin que nada más se queje:

1. **No existe un estado «Reprogramado»** (HU-E7-01 RN-02 y HU-E7-02 RN-02, las dos
   explícitas). Reprogramar mueve la franja y conserva el estado. El test que lo prueba es el
   que reprograma un turno confirmado y verifica que sigue confirmado.

2. **Los extremos no se solapan.** Un turno de 15 a 16 y otro de 16 a 17 conviven. Tiene que
   coincidir con el rango `[)` de la restricción de exclusión — si el dominio dijera otra cosa,
   la pantalla y la base darían respuestas opuestas sobre el mismo par de turnos.

3. **«Ya transcurrió» se mide contra el fin de la franja, no contra el inicio** (HU-E7-03
   RN-01). Marcar «no se presentó» a los cinco minutos de empezado un turno de una hora sería
   marcarlo mientras el cliente todavía puede llegar.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cheatsheet.contexts.scheduling.domain.turno import (
    MENSAJE_DURACION_DE_TURNO,
    MENSAJE_TURNO_NO_TRANSCURRIO,
    CanalDeReserva,
    EstadoTurno,
    Franja,
    Turno,
    validar_duracion_de_turno,
)
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

INICIO = datetime(2026, 9, 8, 18, 0, tzinfo=UTC)
AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


def turno(**cambios: object) -> Turno:
    base: dict[str, object] = {
        "id": uuid4(),
        "empresa_id": EmpresaId(uuid4()),
        "cliente_id": uuid4(),
        "servicio_id": uuid4(),
        "recurso_id": uuid4(),
        "franja": Franja(inicio=INICIO, duracion_min=60),
    }
    base.update(cambios)
    return Turno(**base)  # type: ignore[arg-type]


def _estado(uno: Turno) -> EstadoTurno:
    """Lee el estado sin que mypy lo estreche al literal del constructor."""
    return uno.estado


class TestFranja:
    def test_los_extremos_no_se_solapan(self) -> None:
        de_tres = Franja(inicio=INICIO, duracion_min=60)
        de_cuatro = Franja(inicio=INICIO + timedelta(hours=1), duracion_min=60)

        assert not de_tres.se_solapa_con(de_cuatro)
        assert not de_cuatro.se_solapa_con(de_tres)

    def test_detecta_el_solapamiento_parcial_en_los_dos_sentidos(self) -> None:
        de_tres = Franja(inicio=INICIO, duracion_min=60)
        pisada = Franja(inicio=INICIO + timedelta(minutes=30), duracion_min=60)

        assert de_tres.se_solapa_con(pisada)
        assert pisada.se_solapa_con(de_tres)

    def test_una_franja_contenida_se_solapa(self) -> None:
        larga = Franja(inicio=INICIO, duracion_min=180)
        corta = Franja(inicio=INICIO + timedelta(hours=1), duracion_min=30)

        assert larga.se_solapa_con(corta)
        assert corta.se_solapa_con(larga)

    def test_rechaza_una_franja_sin_zona_horaria(self) -> None:
        with pytest.raises(EntradaInvalida):
            Franja(inicio=datetime(2026, 9, 8, 18), duracion_min=60)  # noqa: DTZ001 — es el caso

    def test_rechaza_una_duracion_no_positiva(self) -> None:
        with pytest.raises(EntradaInvalida):
            Franja(inicio=INICIO, duracion_min=0)

    def test_rechaza_un_turno_de_mas_de_un_dia(self) -> None:
        # Un `franja_duracion_min` con un cero de más bloquearía la agenda de un recurso
        # durante una semana.
        with pytest.raises(EntradaInvalida):
            Franja(inicio=INICIO, duracion_min=24 * 60 + 1)

    def test_un_inicio_igual_a_ahora_no_empezo_antes(self) -> None:
        franja = Franja(inicio=INICIO, duracion_min=60)

        assert not franja.empieza_antes_de(INICIO)
        assert franja.empieza_antes_de(INICIO + timedelta(seconds=1))

    def test_termino_recien_cuando_llega_el_fin(self) -> None:
        franja = Franja(inicio=INICIO, duracion_min=60)

        assert not franja.ya_termino(INICIO + timedelta(minutes=59))
        assert franja.ya_termino(INICIO + timedelta(minutes=60))


class TestRegistrarAPosteriori:
    """HU-E7-06 RN-07: una atención que ya ocurrió nace como ocurrida."""

    def registrar(self, ahora: datetime) -> Turno:
        return Turno.registrar_a_posteriori(
            id=uuid4(),
            empresa_id=EmpresaId(uuid4()),
            cliente_id=uuid4(),
            servicio_id=uuid4(),
            recurso_id=uuid4(),
            franja=Franja(inicio=INICIO, duracion_min=60),
            ahora=ahora,
        )

    def test_nace_completado_por_panel_y_habilita_facturar(self) -> None:
        uno = self.registrar(INICIO + timedelta(hours=2))

        assert _estado(uno) is EstadoTurno.COMPLETADO
        assert uno.canal_reserva == CanalDeReserva.PANEL
        assert uno.habilita_facturacion

    def test_rechaza_una_franja_que_todavia_no_termino(self) -> None:
        with pytest.raises(EntradaInvalida) as fallo:
            self.registrar(INICIO + timedelta(minutes=30))

        assert str(fallo.value) == MENSAJE_TURNO_NO_TRANSCURRIO

    def test_acepta_una_franja_que_termina_exactamente_ahora(self) -> None:
        uno = self.registrar(INICIO + timedelta(minutes=60))

        assert _estado(uno) is EstadoTurno.COMPLETADO

    def test_la_carga_a_posteriori_no_lleva_intervalo(self) -> None:
        """D96: queda en `None`, que significa «sin intervalo» (HU-E7-06 RN-07)."""
        uno = self.registrar(INICIO + timedelta(hours=2))

        assert uno.intervalo_posterior_min is None


class TestDuracionDelTurno:
    """HU-E7-06 RN-08 y HU-E7-02 RN-08: de 5 a 480 minutos."""

    @pytest.mark.parametrize("minutos", [5, 45, 480])
    def test_acepta_el_rango(self, minutos: int) -> None:
        validar_duracion_de_turno(minutos)

    @pytest.mark.parametrize("minutos", [4, 481, 600])
    def test_rechaza_lo_que_esta_afuera(self, minutos: int) -> None:
        with pytest.raises(EntradaInvalida) as fallo:
            validar_duracion_de_turno(minutos)

        assert str(fallo.value) == MENSAJE_DURACION_DE_TURNO
        assert (
            MENSAJE_DURACION_DE_TURNO == "La duración del turno debe estar entre 5 y 480 minutos."
        )


class TestBloquea:
    """El mismo criterio que las dos restricciones de la base (D96)."""

    def con_intervalo(self, minutos: int | None) -> Turno:
        # 09:00 a 09:30 hora de la agenda (12:00 UTC, UTC-3).
        return turno(
            franja=Franja(inicio=datetime(2026, 9, 8, 12, 0, tzinfo=UTC), duracion_min=30),
            intervalo_posterior_min=minutos,
        )

    def inicio(self, minutos: int) -> datetime:
        return datetime(2026, 9, 8, 12, 0, tzinfo=UTC) + timedelta(minutes=minutos)

    def test_pisar_la_franja_real_siempre_bloquea(self) -> None:
        for intervalo in (None, 0, 10):
            assert self.con_intervalo(intervalo).bloquea(self.inicio(29), 30, 0)

    def test_con_intervalo_el_contiguo_bloquea_hasta_que_pasa_el_margen(self) -> None:
        uno = self.con_intervalo(10)

        assert uno.bloquea(self.inicio(30), 30, 10)
        assert uno.bloquea(self.inicio(39), 30, 10)
        assert not uno.bloquea(self.inicio(40), 30, 10)

    def test_el_margen_del_nuevo_tampoco_puede_pisar_al_siguiente(self) -> None:
        uno = self.con_intervalo(10)

        # Un turno nuevo de 08:20 a 08:50 con intervalo 10 llega hasta las 09:00: contiguo.
        assert not uno.bloquea(self.inicio(-40), 30, 10)
        # Con intervalo 11 su margen llega a las 09:01 y pisa el inicio de este.
        assert uno.bloquea(self.inicio(-40), 30, 11)

    def test_sin_intervalo_los_contiguos_conviven(self) -> None:
        assert not self.con_intervalo(0).bloquea(self.inicio(30), 30, 0)

    def test_un_turno_a_posteriori_solo_bloquea_su_franja_real(self) -> None:
        uno = self.con_intervalo(None)

        assert not uno.bloquea(self.inicio(30), 30, 10)
        assert uno.bloquea(self.inicio(29), 30, 10)


class TestTransiciones:
    def test_reprogramar_conserva_el_estado(self) -> None:
        """HU-E7-02 RN-02. **No existe un estado «Reprogramado»**, y esto lo fija."""
        uno = turno()
        uno.confirmar()

        uno.reprogramar(Franja(inicio=INICIO + timedelta(days=1), duracion_min=60), 0, AHORA)

        assert _estado(uno) is EstadoTurno.CONFIRMADO
        assert uno.franja.inicio == INICIO + timedelta(days=1)
        assert "REPROGRAMADO" not in EstadoTurno.__members__

    def test_reprogramar_fija_de_nuevo_cuando_se_asigno_la_franja(self) -> None:
        """Es lo que usa el recordatorio para no avisar de un turno movido dentro de su ventana."""
        uno = turno(franja_asignada_en=AHORA - timedelta(days=3))
        movido_en = AHORA + timedelta(hours=1)

        uno.reprogramar(Franja(inicio=INICIO + timedelta(days=1), duracion_min=60), 0, movido_en)

        assert uno.franja_asignada_en == movido_en

    def test_la_carga_a_posteriori_nace_con_la_franja_asignada_ahora(self) -> None:
        ahora = INICIO + timedelta(days=1)
        uno = Turno.registrar_a_posteriori(
            id=uuid4(),
            empresa_id=EmpresaId(uuid4()),
            cliente_id=uuid4(),
            servicio_id=uuid4(),
            recurso_id=uuid4(),
            franja=Franja(inicio=INICIO, duracion_min=60),
            ahora=ahora,
        )

        assert uno.franja_asignada_en == ahora

    def test_reprogramar_actualiza_el_intervalo_aplicado(self) -> None:
        uno = turno(intervalo_posterior_min=0)

        uno.reprogramar(Franja(inicio=INICIO + timedelta(days=1), duracion_min=60), 15, AHORA)
        assert uno.intervalo_posterior_min == 15

        # La corrección a posteriori no respeta el intervalo: queda en `None`.
        uno.reprogramar(Franja(inicio=INICIO + timedelta(days=2), duracion_min=60), None, AHORA)
        assert uno.intervalo_posterior_min is None

    def test_un_turno_nuevo_nace_con_intervalo_cero(self) -> None:
        assert turno().intervalo_posterior_min == 0

    def test_un_turno_cancelado_no_se_reprograma(self) -> None:
        uno = turno()
        uno.cancelar()

        with pytest.raises(InvarianteViolada):
            uno.reprogramar(Franja(inicio=INICIO + timedelta(days=1), duracion_min=60), 0, AHORA)

    def test_un_turno_cancelado_no_vuelve(self) -> None:
        uno = turno()
        uno.cancelar()

        with pytest.raises(InvarianteViolada):
            uno.confirmar()

    def test_un_turno_completado_no_pasa_a_no_show(self) -> None:
        """Cambiar el pasado registrado es lo que la bitácora de RN-03 existe para impedir."""
        uno = turno()
        despues = INICIO + timedelta(hours=2)
        uno.marcar_completado(despues)

        with pytest.raises(InvarianteViolada):
            uno.marcar_no_show(despues)

    def test_un_turno_pasado_sin_marcar_se_puede_cancelar(self) -> None:
        # Deliberado: si no, los turnos viejos quedarían en RESERVADO para siempre, que es
        # ruido en toda consulta de ocupación.
        uno = turno()
        uno.cancelar()

        assert _estado(uno) is EstadoTurno.CANCELADO


class TestAsistencia:
    def test_no_deja_marcar_un_turno_que_todavia_no_termino(self) -> None:
        uno = turno()
        # Cinco minutos después de empezado un turno de una hora: empezó, pero el cliente
        # todavía puede llegar.
        durante = INICIO + timedelta(minutes=5)

        with pytest.raises(InvarianteViolada) as fallo:
            uno.marcar_no_show(durante)

        # HU-E7-03, primer criterio, letra por letra.
        assert str(fallo.value) == MENSAJE_TURNO_NO_TRANSCURRIO

    def test_deja_marcar_apenas_termina(self) -> None:
        uno = turno()
        uno.marcar_completado(INICIO + timedelta(minutes=60))

        assert _estado(uno) is EstadoTurno.COMPLETADO

    def test_solo_el_completado_habilita_facturar(self) -> None:
        """HU-E7-03 RN-02. Es una propiedad y no un flag guardado: un dato derivado que se
        guarda igual es un dato que algún día va a discrepar."""
        completado = turno()
        completado.marcar_completado(INICIO + timedelta(hours=2))
        no_show = turno()
        no_show.marcar_no_show(INICIO + timedelta(hours=2))

        assert completado.habilita_facturacion
        assert not no_show.habilita_facturacion
        assert not turno().habilita_facturacion


class TestSena:
    def test_asocia_la_sena_una_sola_vez(self) -> None:
        uno = turno()
        cobro = uuid4()
        uno.asignar_cobro(cobro)
        # Reasignar el **mismo** cobro es idempotente: un reintento no es un error.
        uno.asignar_cobro(cobro)

        assert uno.cobro_id == cobro

    def test_rechaza_una_segunda_sena_distinta(self) -> None:
        # Sobrescribir la primera dejaría un cobro cobrado sin turno que lo explique.
        uno = turno()
        uno.asignar_cobro(uuid4())

        with pytest.raises(InvarianteViolada):
            uno.asignar_cobro(uuid4())


def test_el_canal_por_defecto_es_el_panel() -> None:
    """HU-E7-06 RN-02: lo que distingue un turno creado a mano del que va a crear el agente."""
    assert turno().canal_reserva == CanalDeReserva.PANEL
