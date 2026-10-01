"""`planificar_correccion` — HU-E4-05 RN-09, el plan de corrección de datos existentes.

La función es pura: se le da lo que hay guardado y devuelve qué cambiar y qué no tocar.
Lo que se prueba con más insistencia es lo que *no* se cambia (colisiones, nombres que
quedarían inválidos, servicios con duración fuera de regla) y la idempotencia.
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID, uuid4

from cheatsheet.contexts.master_data.domain.correccion import (
    Cambio,
    EntidadCorregible,
    MotivoDeOmision,
    NombreRegistrado,
    planificar_correccion,
)
from cheatsheet.contexts.master_data.domain.valores import AmbitoDeCategoria
from cheatsheet.shared.fiscal import CUIT

CUIT_DE_EMPRESA = CUIT("30712345671")


def _cliente(nombre: str, cuit: CUIT | None = None) -> NombreRegistrado:
    return NombreRegistrado(entidad=EntidadCorregible.CLIENTE, id=uuid4(), nombre=nombre, cuit=cuit)


def _servicio(nombre: str, *, duracion_valida: bool = True) -> NombreRegistrado:
    return NombreRegistrado(
        entidad=EntidadCorregible.SERVICIO,
        id=uuid4(),
        nombre=nombre,
        duracion_valida=duracion_valida,
    )


def _categoria(
    nombre: str, aplica_a: AmbitoDeCategoria = AmbitoDeCategoria.CLIENTE
) -> NombreRegistrado:
    return NombreRegistrado(
        entidad=EntidadCorregible.CATEGORIA, id=uuid4(), nombre=nombre, aplica_a=aplica_a
    )


def _nuevos_nombres(cambios: Iterable[Cambio]) -> dict[UUID, str]:
    return {c.id: c.normalizado for c in cambios}


def test_corrige_cliente_servicio_y_cliente_con_cuit_de_empresa() -> None:
    persona = _cliente("JUAN PEREZ")
    empresa = _cliente("ferreteria lopez s.r.l.", CUIT_DE_EMPRESA)
    servicio = _servicio("CORTE DE PELO")

    plan = planificar_correccion([persona, empresa, servicio])

    assert _nuevos_nombres(plan.cambios) == {
        persona.id: "Juan Perez",
        empresa.id: "Ferreteria Lopez S.R.L.",
        servicio.id: "Corte de pelo",
    }
    assert plan.omisiones == ()
    original = {c.id: c.original for c in plan.cambios}
    assert original[persona.id] == "JUAN PEREZ"


def test_un_nombre_ya_normalizado_no_genera_cambio() -> None:
    plan = planificar_correccion([_cliente("Juan Perez"), _servicio("Corte de pelo")])

    assert plan.cambios == ()
    assert plan.omisiones == ()


def test_planificar_sobre_el_resultado_aplicado_da_cero_cambios() -> None:
    registros = [
        _cliente("  JUAN   PEREZ "),
        _servicio("CORTE DE PELO"),
        _categoria("VIP  GOLD"),
    ]
    primero = planificar_correccion(registros)
    por_id = {c.id: c.normalizado for c in primero.cambios}
    aplicados = [
        NombreRegistrado(
            entidad=r.entidad,
            id=r.id,
            nombre=por_id.get(r.id, r.nombre),
            cuit=r.cuit,
            aplica_a=r.aplica_a,
        )
        for r in registros
    ]

    segundo = planificar_correccion(aplicados)

    assert len(primero.cambios) == 3
    assert segundo.cambios == ()
    assert segundo.omisiones == ()


def test_dos_categorias_que_chocan_en_el_mismo_ambito_se_omiten() -> None:
    sucia = _categoria("Vip  Gold")
    limpia = _categoria("Vip gold")

    plan = planificar_correccion([sucia, limpia])

    assert plan.cambios == ()
    assert [(o.id, o.motivo) for o in plan.omisiones] == [
        (sucia.id, MotivoDeOmision.COLISION_DE_CATEGORIA)
    ]


def test_el_mismo_nombre_en_otro_ambito_si_se_corrige() -> None:
    sucia = _categoria("Vip  Gold", AmbitoDeCategoria.CLIENTE)
    otra = _categoria("Vip gold", AmbitoDeCategoria.AMBOS)

    plan = planificar_correccion([sucia, otra])

    assert _nuevos_nombres(plan.cambios) == {sucia.id: "Vip Gold"}
    assert plan.omisiones == ()


def test_dos_categorias_viejas_que_normalizan_a_la_misma_clave_se_omiten_las_dos() -> None:
    una = _categoria("Vip  Gold")
    otra = _categoria("VIP GOLD")

    plan = planificar_correccion([una, otra])

    assert plan.cambios == ()
    assert {o.id for o in plan.omisiones} == {una.id, otra.id}
    assert {o.motivo for o in plan.omisiones} == {MotivoDeOmision.COLISION_DE_CATEGORIA}


def test_nombre_de_solo_caracteres_invisibles_es_invalido() -> None:
    registro = _cliente("\u200b\u200b")

    plan = planificar_correccion([registro])

    assert plan.cambios == ()
    assert [(o.id, o.motivo) for o in plan.omisiones] == [
        (registro.id, MotivoDeOmision.NOMBRE_INVALIDO)
    ]


def test_categoria_que_pasa_el_maximo_al_normalizar_es_invalida() -> None:
    # 60 caracteres; «İ».lower() son dos, así que al normalizar quedan más de 60.
    registro = _categoria("\u0130" * 60)

    plan = planificar_correccion([registro])

    assert plan.cambios == ()
    assert [(o.id, o.motivo) for o in plan.omisiones] == [
        (registro.id, MotivoDeOmision.NOMBRE_INVALIDO)
    ]


def test_servicio_con_duracion_fuera_de_regla_se_omite() -> None:
    registro = _servicio("CORTE DE PELO", duracion_valida=False)

    plan = planificar_correccion([registro])

    assert plan.cambios == ()
    assert [(o.id, o.motivo) for o in plan.omisiones] == [
        (registro.id, MotivoDeOmision.DURACION_FUERA_DE_REGLA)
    ]


def test_servicio_ya_normalizado_con_duracion_mala_no_se_informa() -> None:
    plan = planificar_correccion([_servicio("Corte de pelo", duracion_valida=False)])

    assert plan.cambios == ()
    assert plan.omisiones == ()


def test_los_conteos_resumen_el_plan() -> None:
    plan = planificar_correccion(
        [
            _cliente("JUAN PEREZ"),
            _servicio("CORTE", duracion_valida=False),
            _categoria("Vip  Gold"),
            _categoria("Vip gold"),
            _categoria("\u0130" * 60),
        ]
    )

    assert dict(plan.conteos()) == {
        "clientes": 1,
        "servicios": 0,
        "categorias": 0,
        "omitidos_colision": 1,
        "omitidos_nombre_invalido": 1,
        "omitidos_duracion": 1,
    }
