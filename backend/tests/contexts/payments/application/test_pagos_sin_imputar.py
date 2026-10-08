"""HS-T1 — un pago se ata a su cobro por `external_reference`, y el que no se puede imputar queda
registrado (unidad `pagos-sin-cobro-asociado`).

Los dobles son los de `test_confirmacion.py`, que también define el del registro nuevo.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from cheatsheet.contexts.payments.application.confirmacion import ConfirmarPago
from cheatsheet.contexts.payments.domain.cobro import Cobro, EstadoCobro, LinkDePago
from cheatsheet.contexts.payments.domain.pago_sin_imputar import MotivoSinImputar, PagoSinImputar
from cheatsheet.shared.auditoria import Resultado
from cheatsheet.shared.empresa import EmpresaId

from tests.contexts.payments.application.test_confirmacion import (
    CobrosFalsos,
    PagosSinImputarFalsos,
    PasarelaFalsa,
    PublicadorFalso,
    SaldosFalsos,
)

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
LINK_VIGENTE = LinkDePago(preference_id="pref-vigente", url="https://mp.com/checkout/vigente")


def _cobro(*, link: LinkDePago | None = LINK_VIGENTE) -> Cobro:
    cobro = Cobro(
        id=uuid4(),
        empresa_id=EMPRESA,
        cliente_id=uuid4(),
        monto=Decimal("1210.00"),
        descripcion="Consulta de octubre",
        vence_el=AHORA + timedelta(days=30),
        created_at=AHORA,
        comprobante_id=uuid4(),
    )
    if link is not None:
        cobro.asignar_link(link, AHORA)
    return cobro


def _confirmar(
    cobros: CobrosFalsos,
    pasarela: PasarelaFalsa,
    publicador: PublicadorFalso | None = None,
    registro: PagosSinImputarFalsos | None = None,
    saldos: SaldosFalsos | None = None,
) -> ConfirmarPago:
    return ConfirmarPago(
        cobros=cobros,
        pasarela=pasarela,
        saldos=saldos or SaldosFalsos(),
        publicador=publicador or PublicadorFalso(),
        sin_imputar=registro or PagosSinImputarFalsos(),
    )


# ------------------------------------------------------------------ encontrar el cobro


async def test_un_pago_con_referencia_y_sin_preferencia_aprueba_el_cobro() -> None:
    """Caso 2. Es el pago real de Checkout Pro: trae `external_reference` y no `preference_id`."""
    cobros, saldos, publicador = CobrosFalsos(), SaldosFalsos(), PublicadorFalso()
    cobro = _cobro()
    await cobros.agregar(cobro)
    pasarela = PasarelaFalsa(preferencia=None, referencia=str(cobro.id))

    resultado = await _confirmar(cobros, pasarela, publicador, saldos=saldos).ejecutar(
        empresa_id=EMPRESA, payment_id="pago-1", ahora=AHORA
    )

    assert resultado.aprobado
    assert cobro.estado is EstadoCobro.APROBADO
    assert cobro.mp_payment_id == "pago-1"
    assert len(saldos.descuentos) == 1
    assert publicador.eventos[0].accion == "confirmar_pago"  # type: ignore[attr-defined]


async def test_un_pago_por_el_link_viejo_se_imputa_al_cobro_de_la_referencia() -> None:
    """Regenerar el link cambia la preferencia de la fila; la referencia sigue siendo la misma."""
    cobros = CobrosFalsos()
    cobro = _cobro(link=LinkDePago(preference_id="pref-nueva", url="https://mp.com/n"))
    await cobros.agregar(cobro)
    pasarela = PasarelaFalsa(preferencia="pref-vieja", referencia=str(cobro.id))

    resultado = await _confirmar(cobros, pasarela).ejecutar(
        empresa_id=EMPRESA, payment_id="pago-1", ahora=AHORA
    )

    assert resultado.aprobado
    assert cobro.estado is EstadoCobro.APROBADO


async def test_un_pago_con_la_preferencia_y_sin_referencia_se_sigue_encontrando() -> None:
    """Caso 3. Compatibilidad con el camino anterior."""
    cobros = CobrosFalsos()
    cobro = _cobro()
    await cobros.agregar(cobro)
    pasarela = PasarelaFalsa(preferencia="pref-vigente", referencia=None)

    resultado = await _confirmar(cobros, pasarela).ejecutar(
        empresa_id=EMPRESA, payment_id="pago-1", ahora=AHORA
    )

    assert resultado.aprobado
    assert cobro.estado is EstadoCobro.APROBADO


# ------------------------------------------------------------------ lo que no se puede imputar


@pytest.mark.parametrize(
    "referencia",
    [
        pytest.param(None, id="sin-referencia"),
        pytest.param("no-es-un-uuid", id="no-es-uuid"),
        pytest.param(str(uuid4()), id="uuid-sin-cobro"),
    ],
)
async def test_un_pago_aprobado_sin_cobro_queda_registrado_y_alertado(
    referencia: str | None,
) -> None:
    """Caso 4. Antes se perdía en un log `info`; ahora es una fila y un evento de severidad alta."""
    cobros, publicador, registro = CobrosFalsos(), PublicadorFalso(), PagosSinImputarFalsos()
    pasarela = PasarelaFalsa(preferencia=None, referencia=referencia, monto=Decimal("1210.005"))
    otro = _cobro()
    await cobros.agregar(otro)

    resultado = await _confirmar(cobros, pasarela, publicador, registro).ejecutar(
        empresa_id=EMPRESA, payment_id="pago-9", ahora=AHORA
    )

    assert resultado.sin_imputar
    assert not resultado.aprobado
    pago = registro.registrados["pago-9"]
    assert pago.motivo is MotivoSinImputar.SIN_COBRO
    assert pago.cobro_id is None
    assert pago.referencia_externa == referencia
    assert pago.monto == Decimal("1210.01")
    assert pago.empresa_id == EMPRESA
    evento = publicador.eventos[0]
    assert evento.accion == "pago_sin_imputar"  # type: ignore[attr-defined]
    assert evento.resultado is Resultado.ERROR  # type: ignore[attr-defined]
    assert evento.usuario_id is None  # type: ignore[attr-defined]
    assert evento.entidad_afectada == f"PagoSinImputar:{pago.id}"  # type: ignore[attr-defined]
    assert otro.estado is EstadoCobro.PENDIENTE
    assert cobros.escrituras == []


async def test_un_segundo_pago_sobre_un_cobro_aprobado_queda_como_cobro_ya_pagado() -> None:
    """Caso 5. Entró plata de más: el cobro y el saldo no cambian, y se avisa."""
    cobros, publicador, registro = CobrosFalsos(), PublicadorFalso(), PagosSinImputarFalsos()
    saldos = SaldosFalsos()
    cobro = _cobro()
    await cobros.agregar(cobro)
    pasarela = PasarelaFalsa(preferencia=None, referencia=str(cobro.id))
    confirmar = _confirmar(cobros, pasarela, publicador, registro, saldos)
    await confirmar.ejecutar(empresa_id=EMPRESA, payment_id="pago-1", ahora=AHORA)
    escrituras = len(cobros.escrituras)
    eventos = len(publicador.eventos)

    segundo = await confirmar.ejecutar(empresa_id=EMPRESA, payment_id="pago-2", ahora=AHORA)

    assert segundo.sin_imputar
    assert segundo.cobro is cobro
    pago = registro.registrados["pago-2"]
    assert pago.motivo is MotivoSinImputar.COBRO_YA_PAGADO
    assert pago.cobro_id == cobro.id
    assert cobro.mp_payment_id == "pago-1"
    assert cobro.estado is EstadoCobro.APROBADO
    assert len(cobros.escrituras) == escrituras
    assert len(saldos.descuentos) == 1
    assert len(publicador.eventos) == eventos + 1


async def test_un_monto_distinto_no_aprueba_y_queda_registrado() -> None:
    """Caso 6. `1210.02` contra `1210.01` difiere; el cobro sigue abierto, sin tocar."""
    cobros, publicador, registro = CobrosFalsos(), PublicadorFalso(), PagosSinImputarFalsos()
    saldos = SaldosFalsos()
    cobro = _cobro()
    cobro.monto = Decimal("1210.01")
    await cobros.agregar(cobro)
    pasarela = PasarelaFalsa(preferencia=None, referencia=str(cobro.id), monto=Decimal("1210.02"))

    resultado = await _confirmar(cobros, pasarela, publicador, registro, saldos).ejecutar(
        empresa_id=EMPRESA, payment_id="pago-1", ahora=AHORA
    )

    assert resultado.sin_imputar
    pago = registro.registrados["pago-1"]
    assert pago.motivo is MotivoSinImputar.MONTO_DISTINTO
    assert pago.cobro_id == cobro.id
    assert pago.monto == Decimal("1210.02")
    assert cobro.estado is EstadoCobro.PENDIENTE
    assert cobro.mp_payment_id is None
    assert saldos.descuentos == []
    assert cobros.escrituras == []


async def test_un_monto_igual_tras_redondear_aprueba() -> None:
    """Caso 6. `1210.005` redondea `ROUND_HALF_UP` a `1210.01`: es el mismo monto."""
    cobros, registro = CobrosFalsos(), PagosSinImputarFalsos()
    cobro = _cobro()
    cobro.monto = Decimal("1210.01")
    await cobros.agregar(cobro)
    pasarela = PasarelaFalsa(preferencia=None, referencia=str(cobro.id), monto=Decimal("1210.005"))

    resultado = await _confirmar(cobros, pasarela, registro=registro).ejecutar(
        empresa_id=EMPRESA, payment_id="pago-1", ahora=AHORA
    )

    assert resultado.aprobado
    assert cobro.estado is EstadoCobro.APROBADO
    assert registro.registrados == {}


async def test_un_pago_sin_monto_informado_se_aprueba_como_antes() -> None:
    """Sin `transaction_amount` no hay nada con qué contradecir al cobro."""
    cobros, registro = CobrosFalsos(), PagosSinImputarFalsos()
    cobro = _cobro()
    await cobros.agregar(cobro)
    pasarela = PasarelaFalsa(preferencia=None, referencia=str(cobro.id))

    resultado = await _confirmar(cobros, pasarela, registro=registro).ejecutar(
        empresa_id=EMPRESA, payment_id="pago-1", ahora=AHORA
    )

    assert resultado.aprobado
    assert registro.registrados == {}


@pytest.mark.parametrize("estado", ["pending", "in_process", "rejected", "authorized"])
async def test_un_pago_no_aprobado_sin_cobro_no_se_registra(estado: str) -> None:
    """Caso 7. Solo el aprobado mueve plata."""
    registro, publicador = PagosSinImputarFalsos(), PublicadorFalso()
    pasarela = PasarelaFalsa(estado=estado, preferencia=None)

    resultado = await _confirmar(CobrosFalsos(), pasarela, publicador, registro).ejecutar(
        empresa_id=EMPRESA, payment_id="pago-1", ahora=AHORA
    )

    assert not resultado.aprobado
    assert not resultado.sin_imputar
    assert registro.registrados == {}
    assert publicador.eventos == []


async def test_la_misma_notificacion_dos_veces_deja_una_fila_un_evento_y_una_consulta() -> None:
    """Caso 8 (D20 para los pagos sin imputar): la segunda no llama a MercadoPago."""
    cobros, publicador, registro = CobrosFalsos(), PublicadorFalso(), PagosSinImputarFalsos()
    pasarela = PasarelaFalsa(preferencia=None)
    confirmar = _confirmar(cobros, pasarela, publicador, registro)

    await confirmar.ejecutar(empresa_id=EMPRESA, payment_id="pago-9", ahora=AHORA)
    segunda = await confirmar.ejecutar(empresa_id=EMPRESA, payment_id="pago-9", ahora=AHORA)

    assert segunda.sin_imputar
    assert segunda.ya_procesado
    assert pasarela.consultas == 1
    assert len(registro.registrados) == 1
    assert registro.intentos == 1
    assert len(publicador.eventos) == 1


async def test_si_otra_notificacion_gano_la_carrera_no_hay_segundo_evento() -> None:
    """Dos notificaciones simultáneas: la que pierde el índice único no duplica la alerta."""

    class NoVeLoDelOtroRequest(PagosSinImputarFalsos):
        async def buscar_por_payment_id(self, payment_id: str) -> PagoSinImputar | None:
            del payment_id
            return None  # la lectura previa no lo ve: el otro request lo inserta a la vez

    registro, publicador = NoVeLoDelOtroRequest(), PublicadorFalso()
    await registro.agregar(
        PagoSinImputar(
            id=uuid4(),
            empresa_id=EMPRESA,
            mp_payment_id="pago-9",
            motivo=MotivoSinImputar.SIN_COBRO,
            recibido_en=AHORA,
        )
    )

    resultado = await _confirmar(
        CobrosFalsos(), PasarelaFalsa(preferencia=None), publicador, registro
    ).ejecutar(empresa_id=EMPRESA, payment_id="pago-9", ahora=AHORA)

    assert resultado.sin_imputar
    assert resultado.ya_procesado
    assert publicador.eventos == []


async def test_el_pago_sobre_un_cobro_cancelado_sigue_por_su_camino() -> None:
    """Caso 9. `registrar_pago_huerfano` no cambia: ni fila nueva ni evento nuevo."""
    cobros, publicador, registro = CobrosFalsos(), PublicadorFalso(), PagosSinImputarFalsos()
    cobro = _cobro()
    cobro.cancelar(motivo="El cliente ya pago por transferencia", ahora=AHORA)
    await cobros.agregar(cobro)
    pasarela = PasarelaFalsa(preferencia=None, referencia=str(cobro.id))

    resultado = await _confirmar(cobros, pasarela, publicador, registro).ejecutar(
        empresa_id=EMPRESA, payment_id="pago-1", ahora=AHORA
    )

    assert resultado.huerfano
    assert not resultado.sin_imputar
    assert registro.registrados == {}
    assert [e.accion for e in publicador.eventos] == ["pago_sobre_cobro_cancelado"]  # type: ignore[attr-defined]


# ------------------------------------------------------------------ la carrera entre dos pagos


async def test_el_cobro_hallado_por_referencia_se_lee_con_bloqueo_de_fila() -> None:
    """Dos webhooks con `payment_id` distinto sobre el mismo cobro abierto no pueden aprobarlo
    los dos: el segundo tiene que esperar al primero y ver `APROBADO` (`COBRO_YA_PAGADO`)."""
    cobros = CobrosFalsos()
    cobro = _cobro()
    await cobros.agregar(cobro)
    pasarela = PasarelaFalsa(preferencia=None, referencia=str(cobro.id))

    await _confirmar(cobros, pasarela).ejecutar(
        empresa_id=EMPRESA, payment_id="pago-1", ahora=AHORA
    )

    assert cobros.bloqueados == [cobro.id]


async def test_el_cobro_hallado_por_preferencia_se_lee_con_bloqueo_de_fila() -> None:
    cobros = CobrosFalsos()
    cobro = _cobro()
    await cobros.agregar(cobro)
    pasarela = PasarelaFalsa(preferencia="pref-vigente", referencia=None)

    await _confirmar(cobros, pasarela).ejecutar(
        empresa_id=EMPRESA, payment_id="pago-1", ahora=AHORA
    )

    assert cobros.bloqueados == [cobro.id]
