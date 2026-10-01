"""El agregado `Cliente` — lo que la pantalla no puede aflojar.

Dos reglas viven acá y no en el formulario, y las dos son de HU-E4-01:

- **RN-01**: `origen` se asigna solo y no se edita. La forma de decir eso en un modelo de
  dominio es que la operación no exista, así que el test lo comprueba mirando la interfaz,
  no intentando una llamada que no compila.
- **Nada se borra**: sólo hay `desactivar` y `reactivar`.
"""

from __future__ import annotations

from datetime import timedelta
from inspect import signature
from uuid import uuid4

import pytest
from cheatsheet.contexts.master_data.domain.cliente import Cliente, FiltrosDeCliente, Pagina
from cheatsheet.contexts.master_data.domain.valores import OrigenDato
from cheatsheet.shared.contacto import Email, Telefono
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.fiscal import CUIT, CondicionIVA

from tests.conftest import INSTANTE_FIJO
from tests.contexts.master_data.conftest import CUIT_VALIDO

EMPRESA = EmpresaId(uuid4())


def _cliente(
    *,
    nombre: str = "Panaderia Dona Rosa",
    cuit: CUIT | None = None,
    condicion_iva: CondicionIVA | None = None,
    contacto_whatsapp: Telefono | None = None,
    contacto_email: Email | None = None,
) -> Cliente:
    return Cliente.registrar(
        id=uuid4(),
        empresa_id=EMPRESA,
        nombre=nombre,
        origen=OrigenDato.PANEL,
        momento=INSTANTE_FIJO,
        cuit=cuit,
        condicion_iva=condicion_iva,
        contacto_whatsapp=contacto_whatsapp,
        contacto_email=contacto_email,
    )


def test_registrar_deja_activo_y_fuera_de_la_planilla() -> None:
    """Lo que crea el panel nunca nace marcado como venido de la planilla (ADR-006)."""
    cliente = _cliente()

    assert cliente.activo is True
    assert cliente.presente_en_planilla is False
    assert cliente.referencia_fila_planilla is None
    assert cliente.origen is OrigenDato.PANEL


def test_el_nombre_vacio_no_construye_un_cliente() -> None:
    with pytest.raises(EntradaInvalida, match="nombre"):
        _cliente(nombre="   ")


def test_el_nombre_se_recorta() -> None:
    assert _cliente(nombre="  Rosa  ").nombre == "Rosa"


#: Todo lo que puede cambiar un `Cliente` después de creado.
MUTADORES = (
    "renombrar",
    "actualizar_contacto",
    "actualizar_datos_fiscales",
    "desactivar",
    "reactivar",
)


def _operaciones() -> set[str]:
    return {n for n in dir(Cliente) if not n.startswith("_") and callable(getattr(Cliente, n))}


def test_el_agregado_no_expone_forma_de_cambiar_el_origen() -> None:
    """RN-01. No hay `cambiar_origen`, y ninguna operación lo recibe como parámetro.

    Se comprueba sobre la interfaz porque es ahí donde vive la regla: el día que alguien
    agregue el método o el parámetro, este test es lo que se lo dice. `registrar` queda
    afuera a propósito — es el único lugar donde el origen se declara, una vez.
    """
    assert not [n for n in _operaciones() if "origen" in n]

    for nombre in MUTADORES:
        parametros = signature(getattr(Cliente, nombre)).parameters
        assert "origen" not in parametros, nombre


def test_no_hay_forma_de_borrar_un_cliente() -> None:
    """ADR-007 y el hueco H4 del DER: se desactiva, no se elimina."""
    operaciones = _operaciones()

    assert "desactivar" in operaciones
    assert not [n for n in operaciones if "eliminar" in n or "borrar" in n]


def test_desactivar_y_reactivar_mueven_la_marca_de_tiempo() -> None:
    cliente = _cliente()
    despues = INSTANTE_FIJO + timedelta(hours=1)

    cliente.desactivar(despues)
    assert cliente.activo is False
    assert cliente.actualizado_en == despues

    cliente.reactivar(despues + timedelta(hours=1))
    assert cliente.activo is True


def test_actualizar_contacto_admite_borrar_los_dos() -> None:
    """Un dato de contacto se puede sacar: no todo cliente sigue teniendo WhatsApp."""
    cliente = _cliente(
        contacto_whatsapp=Telefono("+54 9 11 1234-5678"),
        contacto_email=Email("rosa@panaderia.com"),
    )

    cliente.actualizar_contacto(contacto_whatsapp=None, contacto_email=None, momento=INSTANTE_FIJO)

    assert cliente.contacto_whatsapp is None
    assert cliente.contacto_email is None


def test_facturable_con_cuit_exige_los_dos_datos() -> None:
    """Lo que el épico 5 va a mirar antes de intentar una Factura A."""
    sin_nada = _cliente()
    solo_cuit = _cliente(cuit=CUIT(CUIT_VALIDO))
    completo = _cliente(cuit=CUIT(CUIT_VALIDO), condicion_iva=CondicionIVA.RESPONSABLE_INSCRIPTO)

    assert sin_nada.facturable_con_cuit is False
    assert solo_cuit.facturable_con_cuit is False
    assert completo.facturable_con_cuit is True


def test_un_cliente_sin_cuit_es_valido() -> None:
    """La decisión de este Gate 1: HU-E8-01 registra clientes con sólo un teléfono."""
    cliente = _cliente(nombre="Cliente de WhatsApp", contacto_whatsapp=Telefono("1112345678"))

    assert cliente.cuit is None
    assert cliente.condicion_iva is None


def test_los_filtros_normalizan_el_texto_vacio() -> None:
    """Un buscador vacío no es un filtro por cadena vacía, que no encontraría nada."""
    assert FiltrosDeCliente(texto="   ").texto is None
    assert FiltrosDeCliente(texto=" rosa ").texto == "rosa"


@pytest.mark.parametrize("limite", [0, 201])
def test_la_pagina_rechaza_limites_absurdos(limite: int) -> None:
    """Sin tope, un `?limite=100000` es un volcado del catálogo entero en una request."""
    with pytest.raises(EntradaInvalida):
        Pagina(limite=limite)


def test_la_pagina_rechaza_un_desplazamiento_negativo() -> None:
    with pytest.raises(EntradaInvalida):
        Pagina(desplazamiento=-1)


# --- Normalización del nombre (HU-E4-05) ---------------------------------------------


def test_registrar_guarda_el_nombre_normalizado() -> None:
    assert _cliente(nombre="  JUAN  CARLOS DE LA CRUZ ").nombre == "Juan Carlos de la Cruz"


def test_un_cuit_de_empresa_hace_que_el_nombre_sea_razon_social() -> None:
    cliente = _cliente(nombre="ferreteria lopez s.r.l.", cuit=CUIT(CUIT_VALIDO))

    assert cliente.nombre == "Ferreteria Lopez S.R.L."


def test_renombrar_usa_el_cuit_del_cliente() -> None:
    cliente = _cliente(nombre="Ferreteria Lopez", cuit=CUIT(CUIT_VALIDO))

    cliente.renombrar("IBM ARGENTINA SA", INSTANTE_FIJO + timedelta(hours=1))

    assert cliente.nombre == "IBM Argentina SA"


def test_un_nombre_hecho_solo_de_invisibles_es_obligatorio() -> None:
    with pytest.raises(EntradaInvalida, match="obligatorio"):
        _cliente(nombre="\u200b \ufeff\t")


def test_el_largo_maximo_se_mide_despues_de_normalizar() -> None:
    con_espacios = "a" * 150 + " " * 100 + "b" * 40

    assert len(_cliente(nombre=con_espacios).nombre) == 191
