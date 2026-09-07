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
    MENSAJE_TURNO_NO_TRANSCURRIO,
    CanalDeReserva,
    EstadoTurno,
    Franja,
    Turno,
)
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

INICIO = datetime(2026, 9, 8, 18, 0, tzinfo=UTC)


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


class TestTransiciones:
    def test_reprogramar_conserva_el_estado(self) -> None:
        """HU-E7-02 RN-02. **No existe un estado «Reprogramado»**, y esto lo fija."""
        uno = turno()
        uno.confirmar()

        uno.reprogramar(Franja(inicio=INICIO + timedelta(days=1), duracion_min=60))

        assert _estado(uno) is EstadoTurno.CONFIRMADO
        assert uno.franja.inicio == INICIO + timedelta(days=1)
        assert "REPROGRAMADO" not in EstadoTurno.__members__

    def test_un_turno_cancelado_no_se_reprograma(self) -> None:
        uno = turno()
        uno.cancelar()

        with pytest.raises(InvarianteViolada):
            uno.reprogramar(Franja(inicio=INICIO + timedelta(days=1), duracion_min=60))

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
