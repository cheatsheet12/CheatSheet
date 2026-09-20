"""HS-T1 — el webhook de MercadoPago, y sobre todo **que no cobre dos veces**.

Es el archivo más importante del épico. MercadoPago manda la misma notificación varias veces
por diseño y reintenta durante horas ante cualquier cosa que no sea 2xx; un procesamiento que
no sea idempotente convierte eso en una deuda dada por saldada dos veces y en un comprobante
cuyo saldo bajó el doble.

La decisión **D20** se defiende en dos capas y las dos se prueban acá:

1. **La consulta por `payment_id`** antes de hablar con MercadoPago. Es la que evita hasta la
   llamada de red.
2. **La tabla de transiciones**, que no tiene `APROBADO → APROBADO`. Es la que atrapa el caso
   raro de dos ids distintos para el mismo cobro.

El doble cuenta las llamadas a `consultar_pago` a propósito: un sistema que da por saldada una
deuda dos veces lo hace incrementando ese número, y eso es lo que hay que ver.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.payments.application.confirmacion import (
    ConfirmarPago,
    RegistrarWebhookRechazado,
)
from cheatsheet.contexts.payments.application.ports import (
    FiltrosDeCobro,
    MetricasDeCobros,
    PagoRecibido,
)
from cheatsheet.contexts.payments.domain.cobro import Cobro, EstadoCobro, LinkDePago
from cheatsheet.shared.auditoria import EventoAuditable, Resultado
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.events import EventoDeDominio

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
UN_LINK = LinkDePago(preference_id="pref-1", url="https://mp.com/checkout/pref-1")


class CobrosFalsos:
    """El repositorio en memoria.

    **Guarda la referencia, no una copia**, que es donde se aparta del real: el de verdad
    reconstituye un objeto de dominio aparte de la fila del ORM, así que mutar el agregado no
    escribe nada hasta `guardar`. Por eso lo que se afirma acá cuando algo tiene que *no*
    persistirse es `escrituras`, y no el estado del objeto — que este doble ya mutó.
    """

    def __init__(self) -> None:
        self.guardados: dict[UUID, Cobro] = {}
        self.escrituras: list[UUID] = []

    async def agregar(self, cobro: Cobro) -> None:
        self.guardados[cobro.id] = cobro

    async def guardar(self, cobro: Cobro) -> None:
        self.guardados[cobro.id] = cobro
        self.escrituras.append(cobro.id)

    async def buscar_por_id(self, cobro_id: UUID) -> Cobro | None:
        return self.guardados.get(cobro_id)

    async def buscar_por_payment_id(self, payment_id: str) -> Cobro | None:
        return next((c for c in self.guardados.values() if c.mp_payment_id == payment_id), None)

    async def buscar_por_preference_id(self, preference_id: str) -> Cobro | None:
        return next(
            (
                c
                for c in self.guardados.values()
                if c.link is not None and c.link.preference_id == preference_id
            ),
            None,
        )

    async def listar(self, filtros: FiltrosDeCobro) -> list[Cobro]:
        del filtros
        return list(self.guardados.values())

    async def metricas(self, filtros: FiltrosDeCobro) -> MetricasDeCobros:
        del filtros
        return MetricasDeCobros(
            cobrado=Decimal("0.00"), pendiente=Decimal("0.00"), en_mora=Decimal("0.00")
        )

    async def de_comprobante(self, comprobante_id: UUID) -> list[Cobro]:
        return [c for c in self.guardados.values() if c.comprobante_id == comprobante_id]

    async def abiertos_vencidos_a(self, ahora: datetime) -> list[Cobro]:
        return [
            c
            for c in self.guardados.values()
            if c.estado is EstadoCobro.PENDIENTE and c.esta_vencido_a(ahora)
        ]

    async def abiertos(self) -> list[Cobro]:
        return [c for c in self.guardados.values() if c.esta_abierto]


class PasarelaFalsa:
    """Cuenta las consultas: es lo que hace afirmable la propiedad central de D20."""

    def __init__(self, *, estado: str = "approved", preferencia: str | None = "pref-1") -> None:
        self.estado = estado
        self.preferencia = preferencia
        self.consultas = 0
        #: Con qué preferencias se llamó a `invalidar_link`. Lo que hace afirmable RN-03 de
        #: HU-E6-04: que la cancelación no se quedó en una anotación nuestra.
        self.invalidados: list[str] = []

    async def crear_link(
        self, *, empresa_id: EmpresaId, cobro: Cobro, url_de_retorno: str
    ) -> LinkDePago:
        del empresa_id, cobro, url_de_retorno
        return UN_LINK

    async def consultar_pago(self, *, empresa_id: EmpresaId, payment_id: str) -> PagoRecibido:
        del empresa_id
        self.consultas += 1
        return PagoRecibido(
            payment_id=payment_id, preference_id=self.preferencia, estado=self.estado
        )

    async def invalidar_link(
        self, *, empresa_id: EmpresaId, preference_id: str, ahora: datetime
    ) -> None:
        del empresa_id, ahora
        self.invalidados.append(preference_id)

    async def reembolsar(self, *, empresa_id: EmpresaId, payment_id: str, monto: Decimal) -> bool:
        del empresa_id, payment_id, monto
        return True


class SaldosFalsos:
    def __init__(self, saldo: Decimal = Decimal("5000.00")) -> None:
        self.saldo = saldo
        self.descuentos: list[tuple[UUID, Decimal]] = []

    async def saldo_pendiente(self, comprobante_id: UUID) -> Decimal | None:
        del comprobante_id
        return self.saldo

    async def registrar_cobro(self, comprobante_id: UUID, monto: Decimal) -> None:
        self.descuentos.append((comprobante_id, monto))
        self.saldo -= monto


class PublicadorFalso:
    def __init__(self) -> None:
        self.eventos: list[EventoDeDominio] = []

    async def publicar(self, evento: EventoDeDominio) -> None:
        self.eventos.append(evento)


def _cobro(*, comprobante_id: UUID | None = None) -> Cobro:
    cobro = Cobro(
        id=uuid4(),
        empresa_id=EMPRESA,
        cliente_id=uuid4(),
        monto=Decimal("1210.00"),
        descripcion="Consulta de septiembre",
        vence_el=AHORA + timedelta(days=30),
        created_at=AHORA,
        comprobante_id=comprobante_id,
    )
    cobro.asignar_link(UN_LINK, AHORA)
    return cobro


def _confirmar(
    cobros: CobrosFalsos,
    pasarela: PasarelaFalsa,
    saldos: SaldosFalsos,
    publicador: PublicadorFalso,
) -> ConfirmarPago:
    return ConfirmarPago(cobros=cobros, pasarela=pasarela, saldos=saldos, publicador=publicador)


# ------------------------------------------------------------------ el camino feliz


async def test_un_pago_aprobado_cierra_el_cobro_y_corta_los_recordatorios() -> None:
    cobros, pasarela = CobrosFalsos(), PasarelaFalsa()
    cobro = _cobro()
    await cobros.agregar(cobro)

    resultado = await _confirmar(cobros, pasarela, SaldosFalsos(), PublicadorFalso()).ejecutar(
        empresa_id=EMPRESA, payment_id="pago-1", ahora=AHORA
    )

    assert resultado.aprobado
    assert cobro.estado is EstadoCobro.APROBADO
    assert cobro.mp_payment_id == "pago-1"
    # El link deja de estar activo, y la preferencia se conserva: es lo que ata una
    # notificación tardía a esta fila.
    assert not cobro.tiene_link_activo
    assert cobro.link is not None
    assert not cobro.recibe_recordatorios


async def test_el_evento_lleva_iniciador_sistema() -> None:
    """HS-T1 RN-05. `usuario_id` nulo es lo que HS-T5 usa para «lo hizo el sistema»."""
    cobros, publicador = CobrosFalsos(), PublicadorFalso()
    await cobros.agregar(_cobro())

    await _confirmar(cobros, PasarelaFalsa(), SaldosFalsos(), publicador).ejecutar(
        empresa_id=EMPRESA, payment_id="pago-1", ahora=AHORA
    )

    evento = publicador.eventos[0]
    assert evento.usuario_id is None  # type: ignore[attr-defined]


# ------------------------------------------------------------------ idempotencia · D20


async def test_una_notificacion_repetida_no_vuelve_a_cobrar() -> None:
    """**La propiedad que justifica todo el diseño del webhook** (HS-T1 RN-04).

    Y se mira lo correcto: no que el estado siga bien —eso podría estar bien por casualidad—
    sino que **no se haya vuelto a consultar el pago**. Un sistema que da por saldada una
    deuda dos veces lo hace incrementando ese número.
    """
    cobros, pasarela, saldos = CobrosFalsos(), PasarelaFalsa(), SaldosFalsos()
    cobro = _cobro(comprobante_id=uuid4())
    await cobros.agregar(cobro)
    confirmar = _confirmar(cobros, pasarela, saldos, PublicadorFalso())

    await confirmar.ejecutar(empresa_id=EMPRESA, payment_id="pago-1", ahora=AHORA)
    segunda = await confirmar.ejecutar(empresa_id=EMPRESA, payment_id="pago-1", ahora=AHORA)

    assert segunda.ya_procesado
    assert pasarela.consultas == 1
    # Y lo que de verdad importa: el saldo del comprobante bajó **una** vez.
    assert len(saldos.descuentos) == 1


async def test_dos_ids_distintos_sobre_el_mismo_cobro_tampoco_cobran_dos_veces() -> None:
    """La segunda línea de defensa: la tabla de transiciones.

    MercadoPago reintenta con ids distintos cuando reprocesa. La consulta por `payment_id` no
    lo atrapa, pero `APROBADO → APROBADO` no existe — y el caso de uso lo convierte en una
    respuesta y no en un 500 que haría reintentar otra vez.
    """
    cobros, pasarela, saldos = CobrosFalsos(), PasarelaFalsa(), SaldosFalsos()
    cobro = _cobro(comprobante_id=uuid4())
    await cobros.agregar(cobro)
    confirmar = _confirmar(cobros, pasarela, saldos, PublicadorFalso())

    await confirmar.ejecutar(empresa_id=EMPRESA, payment_id="pago-1", ahora=AHORA)
    segunda = await confirmar.ejecutar(empresa_id=EMPRESA, payment_id="pago-2", ahora=AHORA)

    assert segunda.ya_procesado
    assert cobro.mp_payment_id == "pago-1"
    assert len(saldos.descuentos) == 1


# ------------------------------------------------------------------ lo que no es un pago


async def test_un_pago_pendiente_no_cierra_nada() -> None:
    """`pending`, `in_process` y `authorized` llegan por el mismo webhook que `approved`.

    Tratarlos como pago sería dar por saldada una deuda que todavía puede rechazarse.
    """
    cobros = CobrosFalsos()
    cobro = _cobro()
    await cobros.agregar(cobro)

    resultado = await _confirmar(
        cobros, PasarelaFalsa(estado="pending"), SaldosFalsos(), PublicadorFalso()
    ).ejecutar(empresa_id=EMPRESA, payment_id="pago-1", ahora=AHORA)

    assert not resultado.aprobado
    assert cobro.estado is EstadoCobro.PENDIENTE


async def test_una_notificacion_de_otra_cuenta_no_es_un_error() -> None:
    """MercadoPago manda eventos de la cuenta entera, y una empresa puede cobrar por fuera."""
    resultado = await _confirmar(
        CobrosFalsos(), PasarelaFalsa(preferencia="pref-ajena"), SaldosFalsos(), PublicadorFalso()
    ).ejecutar(empresa_id=EMPRESA, payment_id="pago-1", ahora=AHORA)

    assert not resultado.aprobado
    assert resultado.cobro is None


async def test_un_pago_sin_preferencia_no_se_puede_atar_a_nada() -> None:
    resultado = await _confirmar(
        CobrosFalsos(), PasarelaFalsa(preferencia=None), SaldosFalsos(), PublicadorFalso()
    ).ejecutar(empresa_id=EMPRESA, payment_id="pago-1", ahora=AHORA)

    assert not resultado.aprobado


# ------------------------------------------------------------------ el saldo · RN-03


async def test_un_cobro_con_comprobante_le_baja_el_saldo_al_aprobarse() -> None:
    """HS-T1 RN-03 y **decisión D26**: acá y en ningún otro lado."""
    cobros, saldos = CobrosFalsos(), SaldosFalsos()
    comprobante = uuid4()
    await cobros.agregar(_cobro(comprobante_id=comprobante))

    await _confirmar(cobros, PasarelaFalsa(), saldos, PublicadorFalso()).ejecutar(
        empresa_id=EMPRESA, payment_id="pago-1", ahora=AHORA
    )

    assert saldos.descuentos == [(comprobante, Decimal("1210.00"))]


async def test_un_cobro_sin_comprobante_no_toca_ningun_saldo() -> None:
    cobros, saldos = CobrosFalsos(), SaldosFalsos()
    await cobros.agregar(_cobro())

    await _confirmar(cobros, PasarelaFalsa(), saldos, PublicadorFalso()).ejecutar(
        empresa_id=EMPRESA, payment_id="pago-1", ahora=AHORA
    )

    assert saldos.descuentos == []


# ------------------------------------------------------------------ firma inválida · D22


# ------------------------------------------------------------------ el pago huerfano


async def test_un_pago_sobre_un_cobro_cancelado_no_se_traga_en_silencio() -> None:
    """HU-E6-04. **El agujero que esta unidad cierra.**

    Antes esto caía en la rama de idempotencia: 200, un `logger.info` y nada más. La plata
    quedaba en MercadoPago sin fila que la explicara y sin nadie enterado.
    """
    cobros, publicador = CobrosFalsos(), PublicadorFalso()
    cobro = _cobro()
    cobro.cancelar(motivo="El cliente ya pago por transferencia", ahora=AHORA)
    await cobros.agregar(cobro)

    resultado = await _confirmar(cobros, PasarelaFalsa(), SaldosFalsos(), publicador).ejecutar(
        empresa_id=EMPRESA, payment_id="pago-1", ahora=AHORA
    )

    assert resultado.huerfano
    assert not resultado.aprobado
    assert not resultado.ya_procesado
    # El cobro no resucita: alguien lo dio de baja con un motivo escrito.
    assert cobro.estado is EstadoCobro.CANCELADO
    assert cobro.mp_payment_id == "pago-1"
    assert cobro.tiene_pago_huerfano

    evento = publicador.eventos[-1]
    assert isinstance(evento, EventoAuditable)
    assert evento.accion == "pago_sobre_cobro_cancelado"
    # `Resultado.ERROR` es lo que `NotificarPorEventos` convierte en aviso de severidad alta.
    assert evento.resultado is Resultado.ERROR
    assert evento.usuario_id is None


async def test_el_pago_huerfano_no_avisa_dos_veces() -> None:
    """MercadoPago reintenta por diseño. El `payment_id` guardado corta el segundo (D20)."""
    cobros, publicador = CobrosFalsos(), PublicadorFalso()
    cobro = _cobro()
    cobro.cancelar(motivo="El cliente ya pago por transferencia", ahora=AHORA)
    await cobros.agregar(cobro)
    caso = _confirmar(cobros, PasarelaFalsa(), SaldosFalsos(), publicador)

    primero = await caso.ejecutar(empresa_id=EMPRESA, payment_id="pago-1", ahora=AHORA)
    segundo = await caso.ejecutar(empresa_id=EMPRESA, payment_id="pago-1", ahora=AHORA)

    assert primero.huerfano
    assert segundo.ya_procesado
    assert not segundo.huerfano
    errores = [
        uno
        for uno in publicador.eventos
        if isinstance(uno, EventoAuditable) and uno.resultado is Resultado.ERROR
    ]
    assert len(errores) == 1


async def test_el_pago_huerfano_no_le_baja_el_saldo_al_comprobante() -> None:
    """D26: esa plata no está imputada a nada, y el balance del épico 9 no debe creerlo."""
    cobros, saldos = CobrosFalsos(), SaldosFalsos()
    cobro = _cobro(comprobante_id=uuid4())
    cobro.cancelar(motivo="El cliente ya pago por transferencia", ahora=AHORA)
    await cobros.agregar(cobro)

    await _confirmar(cobros, PasarelaFalsa(), saldos, PublicadorFalso()).ejecutar(
        empresa_id=EMPRESA, payment_id="pago-1", ahora=AHORA
    )

    assert saldos.descuentos == []
    assert saldos.saldo == Decimal("5000.00")


async def test_un_pago_sobre_un_cobro_reembolsado_sigue_siendo_idempotencia() -> None:
    """La rama vieja no se tocó: sólo `CANCELADO` se desvía, y sin alerta acá."""
    cobros, publicador = CobrosFalsos(), PublicadorFalso()
    cobro = _cobro()
    cobro.aprobar(payment_id="pago-viejo", ahora=AHORA)
    cobro.solicitar_reembolso(monto=cobro.monto, ahora=AHORA)
    cobro.confirmar_reembolso(monto=cobro.monto, ahora=AHORA)
    await cobros.agregar(cobro)

    resultado = await _confirmar(cobros, PasarelaFalsa(), SaldosFalsos(), publicador).ejecutar(
        empresa_id=EMPRESA, payment_id="pago-nuevo", ahora=AHORA
    )

    assert resultado.ya_procesado
    assert not resultado.huerfano
    assert publicador.eventos == []


async def test_un_webhook_rechazado_queda_registrado() -> None:
    """HS-T1 RN-01. Se registra el intento; el 200 lo decide el router (D22)."""
    publicador = PublicadorFalso()

    await RegistrarWebhookRechazado(publicador).ejecutar(
        empresa_id=EMPRESA, motivo="firma_invalida", ahora=AHORA
    )

    evento = publicador.eventos[0]
    assert evento.accion == "webhook_rechazado"  # type: ignore[attr-defined]
    assert evento.usuario_id is None  # type: ignore[attr-defined]
