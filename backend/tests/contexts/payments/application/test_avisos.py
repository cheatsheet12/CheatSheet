"""`AvisarPagoConfirmado`: el aviso al cliente cuando un cobro quedó aprobado (HU-E8-04 RN-01).

El caso de uso arma lo que se le dice al cliente a partir del cobro y de su contacto, y se lo pasa
al puerto de aviso. Lo que se afirma es que **nunca levanta** (un fallo del canal no puede voltear
un pago ya guardado), que sin teléfono no hay a quién escribirle, que la seña de un turno avisa
igual y que ningún log lleva datos personales.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.payments.application.avisos import AvisarPagoConfirmado
from cheatsheet.contexts.payments.application.confirmacion import ResultadoDeConfirmacion
from cheatsheet.contexts.payments.application.ports_envio import (
    ContactoDeCobro,
    DatosDeAvisoDePago,
)
from cheatsheet.contexts.payments.domain.cobro import Cobro
from cheatsheet.shared.empresa import EmpresaId
from structlog.testing import capture_logs

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
TELEFONO = "5491155550000"
NOMBRE = "Rosa Diaz"


def _cobro(*, turno_id: UUID | None = None, monto: str = "12500.00") -> Cobro:
    return Cobro(
        id=uuid4(),
        empresa_id=EMPRESA,
        cliente_id=uuid4(),
        monto=Decimal(monto),
        descripcion="Cuota de octubre",
        vence_el=AHORA + timedelta(days=5),
        created_at=AHORA,
        turno_id=turno_id,
    )


class ContactosFalsos:
    def __init__(self, contacto: ContactoDeCobro | None = None, *, falla: bool = False) -> None:
        self._contacto = contacto
        self._falla = falla
        self.consultados: list[UUID] = []

    async def contacto_de(self, cliente_id: UUID) -> ContactoDeCobro | None:
        self.consultados.append(cliente_id)
        if self._falla:
            raise RuntimeError(f"la base se cayo para {TELEFONO}")
        return self._contacto


class AvisoFalso:
    def __init__(self, *, falla: bool = False) -> None:
        self._falla = falla
        self.avisos: list[DatosDeAvisoDePago] = []

    async def avisar(self, datos: DatosDeAvisoDePago) -> None:
        self.avisos.append(datos)
        if self._falla:
            raise RuntimeError(f"Meta rechazo {TELEFONO}")


def _caso(contactos: ContactosFalsos, aviso: AvisoFalso) -> AvisarPagoConfirmado:
    return AvisarPagoConfirmado(contactos=contactos, aviso=aviso)


CONTACTO = ContactoDeCobro(nombre=NOMBRE, telefono=TELEFONO)


async def test_avisa_al_cliente_con_los_datos_del_cobro() -> None:
    cobro, aviso = _cobro(), AvisoFalso()

    await _caso(ContactosFalsos(CONTACTO), aviso).ejecutar(cobro=cobro)

    assert aviso.avisos == [
        DatosDeAvisoDePago(
            cobro_id=cobro.id,
            cliente_id=cobro.cliente_id,
            nombre=NOMBRE,
            telefono=TELEFONO,
            concepto="Cuota de octubre",
            monto=Decimal("12500.00"),
        )
    ]


async def test_la_sena_de_un_turno_avisa_igual() -> None:
    """Decisión 4: una seña es un cobro, y RN-01 no distingue."""
    cobro, aviso = _cobro(turno_id=uuid4()), AvisoFalso()

    await _caso(ContactosFalsos(CONTACTO), aviso).ejecutar(cobro=cobro)

    assert [una.cobro_id for una in aviso.avisos] == [cobro.id]


async def test_cliente_sin_telefono_no_avisa() -> None:
    cobro, aviso = _cobro(), AvisoFalso()

    with capture_logs() as registros:
        await _caso(ContactosFalsos(None), aviso).ejecutar(cobro=cobro)

    assert aviso.avisos == []
    assert [r["event"] for r in registros] == ["aviso_de_pago_sin_telefono"]


async def test_una_falla_del_puerto_no_levanta_y_no_filtra_datos_personales() -> None:
    cobro = _cobro()

    with capture_logs() as registros:
        await _caso(ContactosFalsos(CONTACTO), AvisoFalso(falla=True)).ejecutar(cobro=cobro)

    (registro,) = registros
    assert registro["event"] == "aviso_de_pago_fallido"
    assert registro["causa"] == "RuntimeError"
    assert TELEFONO not in str(registros)
    assert NOMBRE not in str(registros)


async def test_una_falla_al_leer_el_contacto_no_levanta() -> None:
    aviso = AvisoFalso()

    with capture_logs() as registros:
        await _caso(ContactosFalsos(falla=True), aviso).ejecutar(cobro=_cobro())

    assert aviso.avisos == []
    assert [r["event"] for r in registros] == ["aviso_de_pago_fallido"]
    assert TELEFONO not in str(registros)


# ------------------------------------------------------- cuándo corresponde avisar


@pytest.mark.parametrize(
    ("resultado", "corresponde"),
    [
        (ResultadoDeConfirmacion(aprobado=True, cobro=_cobro()), True),
        (ResultadoDeConfirmacion(aprobado=True, ya_procesado=True, cobro=_cobro()), False),
        (ResultadoDeConfirmacion(aprobado=False, huerfano=True, cobro=_cobro()), False),
        (ResultadoDeConfirmacion(aprobado=False), False),
        (ResultadoDeConfirmacion(aprobado=True), False),
    ],
    ids=["aprobado_ahora", "repetido", "huerfano", "no_aprobado", "sin_cobro"],
)
async def test_solo_corresponde_avisar_si_se_aprobo_en_este_request(
    resultado: ResultadoDeConfirmacion, corresponde: bool
) -> None:
    assert resultado.recien_aprobado is corresponde
