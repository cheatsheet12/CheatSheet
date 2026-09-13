"""`RecursoReservable` — el horario de atención, sin base de datos (HU-E7-04, HU-E7-05).

Lo que se prueba acá es la única pregunta que este agregado contesta: **¿el recurso atiende en
esta franja?** Cinco cosas de esa respuesta valen un test cada una:

1. Un turno tiene que entrar **entero** en el horario. El que empieza a las 17:45 y dura media
   hora no entra en un local que cierra a las 18 — aceptarlo sería ofrecer un turno que termina
   con la persiana baja.
2. **La excepción reemplaza al patrón**, no se le suma (RN-03). Si se sumaran, abrir un domingo
   a la mañana abriría también el horario del lunes.
3. Un recurso **sin servicios asociados no admite ninguno**. La alternativa —«sin lista,
   todos»— convierte un recurso a medio configurar en uno que acepta cualquier reserva.
4. Un recurso **desactivado no está disponible nunca**, aunque su horario diga que sí.
5. La franja se compara **en la zona de la agenda**, no en UTC. Un turno de las 22 de un martes
   es del martes para quien lo atiende, aunque en UTC ya sea miércoles — y ese es exactamente
   el error que hace que la agenda se corra un día.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from uuid import uuid4

import pytest
from cheatsheet.contexts.scheduling.domain.recurso import (
    MENSAJE_EXCEPCION_DUPLICADA,
    MENSAJE_HORARIO_INVERTIDO,
    ZONA_DE_LA_AGENDA,
    ExcepcionDeDisponibilidad,
    PatronDeDisponibilidad,
    RecursoReservable,
    TipoExcepcion,
    TipoRecurso,
)
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

#: Martes 8 de septiembre de 2026. Elegido porque es martes: `weekday() == 1`, que es lo que
#: los patrones de estos tests usan.
MARTES = date(2026, 9, 8)


def local(dia: date, hora: int, minuto: int = 0) -> datetime:
    return datetime.combine(dia, time(hora, minuto), tzinfo=ZONA_DE_LA_AGENDA)


def recurso(**cambios: object) -> RecursoReservable:
    base: dict[str, object] = {
        "id": uuid4(),
        "empresa_id": EmpresaId(uuid4()),
        "nombre": "Consultorio 1",
        "tipo": TipoRecurso.ESPACIO,
        "patrones": (
            PatronDeDisponibilidad(
                dia_semana=1, hora_inicio=time(9), hora_fin=time(18), duracion_slot_min=30
            ),
        ),
    }
    base.update(cambios)
    return RecursoReservable(**base)  # type: ignore[arg-type]


class TestPatron:
    def test_rechaza_la_franja_invertida_con_la_frase_de_la_historia(self) -> None:
        with pytest.raises(EntradaInvalida) as fallo:
            PatronDeDisponibilidad(
                dia_semana=1, hora_inicio=time(18), hora_fin=time(9), duracion_slot_min=30
            )

        # HU-E7-04, criterio 3, letra por letra.
        assert str(fallo.value) == MENSAJE_HORARIO_INVERTIDO

    def test_rechaza_un_dia_de_semana_fuera_de_rango(self) -> None:
        with pytest.raises(EntradaInvalida):
            PatronDeDisponibilidad(
                dia_semana=7, hora_inicio=time(9), hora_fin=time(18), duracion_slot_min=30
            )

    def test_rechaza_un_slot_de_cero_minutos(self) -> None:
        # Un slot de cero haría infinita la enumeración de horarios del día.
        with pytest.raises(EntradaInvalida):
            PatronDeDisponibilidad(
                dia_semana=1, hora_inicio=time(9), hora_fin=time(18), duracion_slot_min=0
            )


class TestDisponibilidad:
    def test_acepta_una_franja_que_entra_entera(self) -> None:
        assert recurso().esta_disponible_en(local(MARTES, 15), 30)

    def test_rechaza_la_franja_que_se_pasa_del_cierre(self) -> None:
        # Empieza dentro del horario y termina afuera: es el caso que un `<=` mal puesto deja
        # pasar, y el que produce un turno que termina con el local cerrado.
        assert not recurso().esta_disponible_en(local(MARTES, 17, 45), 30)

    def test_rechaza_el_dia_que_el_recurso_no_atiende(self) -> None:
        miercoles = date(2026, 9, 9)
        assert not recurso().esta_disponible_en(local(miercoles, 15), 30)

    def test_rechaza_una_franja_sin_zona_horaria(self) -> None:
        # Sin zona, dos turnos «a las 15» pueden ser el mismo o distintos según quién los lea.
        with pytest.raises(EntradaInvalida):
            recurso().esta_disponible_en(datetime(2026, 9, 8, 15), 30)  # noqa: DTZ001 — es el caso

    def test_lee_la_franja_en_la_zona_de_la_agenda_y_no_en_utc(self) -> None:
        """Las 22 del martes local son las 01 del miércoles en UTC.

        El recurso atiende los martes. Si la comparación se hiciera en UTC, este instante
        caería en miércoles y el turno se rechazaría — la agenda corrida un día entero, que es
        el bug que nadie encuentra mirando el código.
        """
        de_noche = recurso(
            patrones=(
                PatronDeDisponibilidad(
                    dia_semana=1, hora_inicio=time(20), hora_fin=time(23), duracion_slot_min=60
                ),
            )
        )
        en_utc = local(MARTES, 22).astimezone(UTC)

        assert en_utc.weekday() == 2  # miércoles en UTC
        assert de_noche.esta_disponible_en(en_utc, 60)

    def test_un_recurso_desactivado_no_esta_disponible_nunca(self) -> None:
        apagado = recurso()
        apagado.desactivar()

        assert not apagado.esta_disponible_en(local(MARTES, 15), 30)
        # HU-E7-04 RN-03: desactivar **no toca** lo ya reservado, y por eso el método no
        # recibe ni mira turnos.
        assert apagado.patrones != ()


class TestExcepciones:
    def test_un_bloqueo_cierra_el_dia_aunque_el_patron_diga_que_abre(self) -> None:
        uno = recurso()
        uno.agregar_excepcion(ExcepcionDeDisponibilidad(fecha=MARTES, tipo=TipoExcepcion.BLOQUEO))

        assert not uno.esta_disponible_en(local(MARTES, 15), 30)
        assert uno.horarios_del_dia(MARTES) == ()

    def test_una_apertura_especial_reemplaza_al_patron_en_vez_de_sumarse(self) -> None:
        """RN-03: la excepción **tiene prioridad**, no se acumula.

        El patrón dice 9 a 18. La apertura dice 20 a 22. Después de la excepción, las 15 —que
        el patrón permitía— dejan de estar disponibles: es lo que significa «prioridad».
        """
        uno = recurso()
        uno.agregar_excepcion(
            ExcepcionDeDisponibilidad(
                fecha=MARTES,
                tipo=TipoExcepcion.APERTURA_ESPECIAL,
                franja_inicio=local(MARTES, 20),
                franja_duracion_min=120,
            )
        )

        assert uno.esta_disponible_en(local(MARTES, 20), 60)
        assert not uno.esta_disponible_en(local(MARTES, 15), 30)

    def test_rechaza_una_segunda_excepcion_para_la_misma_fecha(self) -> None:
        uno = recurso()
        uno.agregar_excepcion(ExcepcionDeDisponibilidad(fecha=MARTES, tipo=TipoExcepcion.BLOQUEO))

        with pytest.raises(InvarianteViolada) as fallo:
            uno.agregar_excepcion(
                ExcepcionDeDisponibilidad(
                    fecha=MARTES,
                    tipo=TipoExcepcion.APERTURA_ESPECIAL,
                    franja_inicio=local(MARTES, 20),
                    franja_duracion_min=60,
                )
            )

        # HU-E7-05, tercer criterio, letra por letra.
        assert str(fallo.value) == MENSAJE_EXCEPCION_DUPLICADA

    def test_quitar_una_excepcion_devuelve_el_dia_a_su_horario_habitual(self) -> None:
        uno = recurso()
        uno.agregar_excepcion(ExcepcionDeDisponibilidad(fecha=MARTES, tipo=TipoExcepcion.BLOQUEO))
        uno.quitar_excepcion(MARTES)

        assert uno.esta_disponible_en(local(MARTES, 15), 30)

    def test_quitar_una_fecha_sin_excepcion_no_falla(self) -> None:
        # El resultado deseado ya se cumple. Fallar obligaría a la pantalla a consultar antes
        # de borrar para no mostrar un error sobre algo que salió bien.
        recurso().quitar_excepcion(MARTES)

    def test_un_bloqueo_con_horario_es_una_fila_ambigua_y_se_rechaza(self) -> None:
        with pytest.raises(EntradaInvalida):
            ExcepcionDeDisponibilidad(
                fecha=MARTES,
                tipo=TipoExcepcion.BLOQUEO,
                franja_inicio=local(MARTES, 20),
                franja_duracion_min=60,
            )

    def test_una_apertura_sin_horario_se_rechaza(self) -> None:
        with pytest.raises(EntradaInvalida):
            ExcepcionDeDisponibilidad(fecha=MARTES, tipo=TipoExcepcion.APERTURA_ESPECIAL)

    def test_una_apertura_cuyo_horario_cae_en_otra_fecha_se_rechaza(self) -> None:
        with pytest.raises(EntradaInvalida):
            ExcepcionDeDisponibilidad(
                fecha=MARTES,
                tipo=TipoExcepcion.APERTURA_ESPECIAL,
                franja_inicio=local(date(2026, 9, 9), 20),
                franja_duracion_min=60,
            )


class TestHorariosDelDia:
    def test_corta_la_franja_en_slots_y_no_ofrece_el_que_se_pasa(self) -> None:
        uno = recurso(
            patrones=(
                PatronDeDisponibilidad(
                    dia_semana=1, hora_inicio=time(9), hora_fin=time(10, 15), duracion_slot_min=30
                ),
            )
        )

        # 9:00 y 9:30 entran; 10:00 terminaría 10:30, después del cierre.
        assert uno.horarios_del_dia(MARTES) == (local(MARTES, 9), local(MARTES, 9, 30))

    def test_no_ofrece_nada_el_dia_que_el_recurso_no_atiende(self) -> None:
        assert recurso().horarios_del_dia(date(2026, 9, 9)) == ()

    def test_la_apertura_especial_hereda_la_duracion_de_slot_del_patron(self) -> None:
        """El DER no le da columna de duración a la excepción, así que la hereda.

        Sin herencia habría que ofrecer la franja entera como un solo turno de dos horas, que
        no es lo que nadie configura cuando abre un sábado excepcional.
        """
        uno = recurso()
        uno.agregar_excepcion(
            ExcepcionDeDisponibilidad(
                fecha=MARTES,
                tipo=TipoExcepcion.APERTURA_ESPECIAL,
                franja_inicio=local(MARTES, 20),
                franja_duracion_min=60,
            )
        )

        assert uno.horarios_del_dia(MARTES) == (local(MARTES, 20), local(MARTES, 20, 30))


class TestServicios:
    def test_un_recurso_sin_servicios_no_admite_ninguno(self) -> None:
        # «Sin lista, todos» convertiría un recurso a medio configurar en uno que acepta
        # cualquier reserva, que es el error que se descubre cuando alguien ya reservó.
        assert not recurso().admite_servicio(uuid4())

    def test_admite_solo_los_asociados(self) -> None:
        corte, color = uuid4(), uuid4()
        uno = recurso()
        uno.asociar_servicios(frozenset({corte}))

        assert uno.admite_servicio(corte)
        assert not uno.admite_servicio(color)

    def test_rechaza_un_recurso_sin_nombre(self) -> None:
        with pytest.raises(EntradaInvalida):
            recurso(nombre="   ")
