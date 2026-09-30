"""Los casos de uso de cobros (HU-E6-01 … HU-E6-06) y los dos barridos (HS-T3, RN-03).

Tres cosas se prueban acá y las tres son decisiones del épico:

- **D26** — un cobro asociado a un comprobante **no descuenta nada al crearse**. El test que
  lo fija es el que mira el saldo después de generar el link y antes de que nadie pague.
- **D25** — la cadena se ancla en el paso, no en la fecha. El test que lo prueba es el del
  planificador atrasado: con tres pasos vencidos manda **uno**, no tres.
- **D27** — un reembolso rechazado deja el cobro en `APROBADO`.

Los dobles se reusan del archivo del webhook: son los mismos puertos, y dos juegos de dobles
para los mismos protocolos serían dos cosas que pueden discrepar.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.payments.application.cobros import (
    MOTIVO_SIN_PERMISO,
    CancelarCobro,
    GenerarCobro,
    ListarCobros,
    MetricasDelPeriodo,
    ReembolsarCobro,
    RegenerarLink,
    VerCobro,
)
from cheatsheet.contexts.payments.application.errors import (
    ClienteInexistente,
    CobroInexistente,
    CobroNoCancelable,
    CobroNoReembolsable,
    ComprobanteDeOtroCliente,
    MontoExcedeSaldo,
    PasarelaNoDisponible,
    RecordatorioDuplicado,
    ReembolsoRechazado,
)
from cheatsheet.contexts.payments.application.ports import (
    FiltrosDeCobro,
    MetricasDeCobros,
    PasoDeCadena,
)
from cheatsheet.contexts.payments.application.recordatorios import (
    DespacharRecordatorios,
    VencerCobros,
)
from cheatsheet.contexts.payments.domain.cobro import Cobro, EstadoCobro, LinkDePago
from cheatsheet.contexts.payments.domain.recordatorio import EstadoEntrega, Recordatorio
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.roles import RolUsuario

from tests.contexts.payments.application.test_confirmacion import (
    CLIENTE,
    UN_LINK,
    ClientesFalsos,
    CobrosFalsos,
    PasarelaFalsa,
    PublicadorFalso,
    SaldosFalsos,
)

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
USUARIO = UsuarioId(uuid4())
URL_RETORNO = "https://panel.cheatsheet.ar/cobros"


class PasarelaCaida(PasarelaFalsa):
    async def crear_link(
        self, *, empresa_id: EmpresaId, cobro: Cobro, url_de_retorno: str
    ) -> LinkDePago:
        del empresa_id, cobro, url_de_retorno
        raise PasarelaNoDisponible("MercadoPago no respondio")


class PasarelaQueNoInvalida(PasarelaFalsa):
    """MercadoPago no confirma que el link murió. HU-E6-04 RN-03: no se cancela nada."""

    async def invalidar_link(
        self, *, empresa_id: EmpresaId, preference_id: str, ahora: datetime
    ) -> None:
        del empresa_id, preference_id, ahora
        raise PasarelaNoDisponible("MercadoPago no invalido el link de pago")


class PasarelaQueRechazaElReembolso(PasarelaFalsa):
    async def reembolsar(self, *, empresa_id: EmpresaId, payment_id: str, monto: Decimal) -> bool:
        del empresa_id, payment_id, monto
        return False


class RecordatoriosFalsos:
    """El índice único vive en la base; acá se simula su efecto, que es lo que importa."""

    def __init__(self) -> None:
        self.guardados: list[Recordatorio] = []

    async def agregar(self, recordatorio: Recordatorio) -> None:
        if any(
            uno.cobro_id == recordatorio.cobro_id and uno.paso == recordatorio.paso
            for uno in self.guardados
        ):
            raise RecordatorioDuplicado("ya salio")
        self.guardados.append(recordatorio)

    async def guardar(self, recordatorio: Recordatorio) -> None:
        pass

    async def de_cobro(self, cobro_id: UUID) -> list[Recordatorio]:
        return [uno for uno in self.guardados if uno.cobro_id == cobro_id]

    async def de_cobros(self, cobro_ids: list[UUID]) -> dict[UUID, list[Recordatorio]]:
        agrupados: dict[UUID, list[Recordatorio]] = {}
        for uno in self.guardados:
            if uno.cobro_id in cobro_ids:
                agrupados.setdefault(uno.cobro_id, []).append(uno)
        return agrupados


class EnvioFalso:
    def __init__(self) -> None:
        self.enviados: list[tuple[UUID, int, str]] = []

    async def enviar(
        self, *, empresa_id: EmpresaId, cobro: Cobro, canal: str, paso: int
    ) -> EstadoEntrega:
        del empresa_id
        self.enviados.append((cobro.id, paso, canal))
        return EstadoEntrega.ENVIADO


class CadenaFalsa:
    def __init__(self, *dias: int) -> None:
        self.pasos_ = tuple(
            PasoDeCadena(dias=uno, canal="WHATSAPP") for uno in (dias or (3, 7, 15))
        )

    async def pasos(self, *, empresa_id: EmpresaId) -> tuple[PasoDeCadena, ...]:
        del empresa_id
        return self.pasos_


def _cobro(*, comprobante_id: UUID | None = None, vence_en_dias: int = 30) -> Cobro:
    cobro = Cobro(
        id=uuid4(),
        empresa_id=EMPRESA,
        cliente_id=uuid4(),
        monto=Decimal("1210.00"),
        descripcion="Consulta de septiembre",
        vence_el=AHORA + timedelta(days=vence_en_dias),
        created_at=AHORA,
        comprobante_id=comprobante_id,
    )
    cobro.asignar_link(UN_LINK, AHORA)
    return cobro


def _generar(
    cobros: CobrosFalsos,
    pasarela: PasarelaFalsa,
    saldos: SaldosFalsos,
    clientes: ClientesFalsos | None = None,
) -> GenerarCobro:
    return GenerarCobro(
        cobros=cobros,
        pasarela=pasarela,
        saldos=saldos,
        clientes=clientes or ClientesFalsos(CLIENTE),
        publicador=PublicadorFalso(),
        url_de_retorno=URL_RETORNO,
    )


# ------------------------------------------------------------------ generar · HU-E6-03


async def test_generar_deja_el_cobro_con_link_activo() -> None:
    cobros = CobrosFalsos()

    cobro = await _generar(cobros, PasarelaFalsa(), SaldosFalsos()).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        cliente_id=CLIENTE,
        monto=Decimal("1210.00"),
        descripcion="Consulta de septiembre",
        ahora=AHORA,
    )

    assert cobro.tiene_link_activo
    assert cobro.estado is EstadoCobro.PENDIENTE
    assert cobros.guardados[cobro.id] is cobro


async def test_si_mercadopago_no_responde_el_cobro_no_se_crea() -> None:
    """El criterio de aceptación, textual: «no crea el cobro».

    Un cobro sin link es una deuda que nadie puede pagar y que igual manda recordatorios.
    """
    cobros = CobrosFalsos()

    with pytest.raises(PasarelaNoDisponible):
        await _generar(cobros, PasarelaCaida(), SaldosFalsos()).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            cliente_id=CLIENTE,
            monto=Decimal("1210.00"),
            descripcion="Consulta",
            ahora=AHORA,
        )

    assert cobros.guardados == {}


async def test_solo_lectura_no_genera_cobros() -> None:
    """HU-E6-01 RN-04: ve el listado, no inicia acciones."""
    with pytest.raises(EntradaInvalida) as exc:
        await _generar(CobrosFalsos(), PasarelaFalsa(), SaldosFalsos()).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.SOLO_LECTURA,
            cliente_id=CLIENTE,
            monto=Decimal("100.00"),
            descripcion="Consulta",
            ahora=AHORA,
        )

    assert str(exc.value) == MOTIVO_SIN_PERMISO


# ------------------------------------------------------------------ el cliente · D92


async def _generar_para(
    cliente_id: UUID,
    *,
    clientes: ClientesFalsos,
    cobros: CobrosFalsos | None = None,
    pasarela: PasarelaFalsa | None = None,
    publicador: PublicadorFalso | None = None,
    rol: RolUsuario = RolUsuario.OPERADOR,
    saldos: SaldosFalsos | None = None,
    comprobante_id: UUID | None = None,
) -> Cobro:
    return await GenerarCobro(
        cobros=cobros or CobrosFalsos(),
        pasarela=pasarela or PasarelaFalsa(),
        saldos=saldos or SaldosFalsos(),
        clientes=clientes,
        publicador=publicador or PublicadorFalso(),
        url_de_retorno=URL_RETORNO,
    ).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=rol,
        cliente_id=cliente_id,
        monto=Decimal("100.00"),
        descripcion="Consulta",
        ahora=AHORA,
        comprobante_id=comprobante_id,
    )


async def test_un_cliente_que_no_existe_no_deja_generar_ni_gasta_una_llamada() -> None:
    """Ni pasarela, ni cobro guardado, ni bitacora: se rechaza antes de todo eso."""
    cobros, pasarela, publicador = CobrosFalsos(), PasarelaFalsa(), PublicadorFalso()

    with pytest.raises(ClienteInexistente) as exc:
        await _generar_para(
            uuid4(),
            clientes=ClientesFalsos(),
            cobros=cobros,
            pasarela=pasarela,
            publicador=publicador,
        )

    assert str(exc.value) == "El cliente seleccionado no existe o esta inactivo."
    assert pasarela.creados == 0
    assert cobros.guardados == {}
    assert publicador.eventos == []


async def test_un_cliente_inactivo_recibe_el_mismo_rechazo() -> None:
    """El puerto colapsa «no existe», «es de otra empresa» e «inactivo» en un solo `False`."""
    with pytest.raises(ClienteInexistente):
        await _generar_para(CLIENTE, clientes=ClientesFalsos())


async def test_un_cliente_activo_genera_el_cobro() -> None:
    cobro = await _generar_para(CLIENTE, clientes=ClientesFalsos(CLIENTE))

    assert cobro.cliente_id == CLIENTE
    assert cobro.tiene_link_activo


async def test_solo_lectura_se_rechaza_antes_de_preguntar_por_el_cliente() -> None:
    """Si el guarda de rol viniera despues, la respuesta dejaria ver si el id existe."""
    clientes = ClientesFalsos()

    with pytest.raises(EntradaInvalida) as exc:
        await _generar_para(uuid4(), clientes=clientes, rol=RolUsuario.SOLO_LECTURA)

    assert str(exc.value) == MOTIVO_SIN_PERMISO
    assert clientes.consultas == []


async def test_un_comprobante_de_otro_cliente_no_deja_generar() -> None:
    """Sin esto, con el selector editable se le cobraria a Ana la factura de Bruno."""
    de_bruno = SaldosFalsos(cliente=uuid4())
    cobros, pasarela, publicador = CobrosFalsos(), PasarelaFalsa(), PublicadorFalso()

    with pytest.raises(ComprobanteDeOtroCliente) as exc:
        await _generar_para(
            CLIENTE,
            clientes=ClientesFalsos(CLIENTE),
            cobros=cobros,
            pasarela=pasarela,
            publicador=publicador,
            saldos=de_bruno,
            comprobante_id=uuid4(),
        )

    assert str(exc.value) == "El comprobante no corresponde al cliente elegido."
    assert pasarela.creados == 0
    assert cobros.guardados == {}
    assert publicador.eventos == []


async def test_un_comprobante_que_no_existe_dice_que_no_existe_y_no_deja_rastro() -> None:
    """`cliente_de` devuelve `None`: no es "de otro cliente", es que no hay comprobante."""

    class SinComprobante(SaldosFalsos):
        async def saldo_pendiente(self, comprobante_id: UUID) -> Decimal | None:
            del comprobante_id
            return None

    cobros, pasarela, publicador = CobrosFalsos(), PasarelaFalsa(), PublicadorFalso()

    with pytest.raises(CobroInexistente) as exc:
        await _generar_para(
            CLIENTE,
            clientes=ClientesFalsos(CLIENTE),
            cobros=cobros,
            pasarela=pasarela,
            publicador=publicador,
            saldos=SinComprobante(cliente=None),
            comprobante_id=uuid4(),
        )

    assert str(exc.value) == "El comprobante no existe"
    assert pasarela.creados == 0
    assert cobros.guardados == {}
    assert publicador.eventos == []


async def test_un_comprobante_del_mismo_cliente_genera_el_cobro() -> None:
    cobro = await _generar_para(
        CLIENTE,
        clientes=ClientesFalsos(CLIENTE),
        saldos=SaldosFalsos(cliente=CLIENTE),
        comprobante_id=uuid4(),
    )

    assert cobro.comprobante_id is not None


# ------------------------------------------------------------------ el comprobante · D26


async def test_generar_un_cobro_asociado_no_descuenta_el_saldo_todavia() -> None:
    """**Decisión D26**, y es el test que la fija.

    Un link generado no es plata cobrada. Un comprobante cuyo saldo bajó porque alguien
    generó un link que nadie pagó miente en el balance del épico 9.
    """
    saldos = SaldosFalsos(Decimal("5000.00"))

    await _generar(CobrosFalsos(), PasarelaFalsa(), saldos).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        cliente_id=CLIENTE,
        monto=Decimal("1210.00"),
        descripcion="Pago parcial",
        ahora=AHORA,
        comprobante_id=uuid4(),
    )

    assert saldos.saldo == Decimal("5000.00")
    assert saldos.descuentos == []


async def test_un_monto_mayor_al_saldo_se_rechaza_y_dice_cuanto_queda() -> None:
    """HU-E6-06 RN-02. El criterio pide que el mensaje **indique el saldo disponible**."""
    with pytest.raises(MontoExcedeSaldo) as exc:
        await _generar(CobrosFalsos(), PasarelaFalsa(), SaldosFalsos(Decimal("500.00"))).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            cliente_id=CLIENTE,
            monto=Decimal("1210.00"),
            descripcion="Pago parcial",
            ahora=AHORA,
            comprobante_id=uuid4(),
        )

    assert "500.00" in str(exc.value)


async def test_un_comprobante_inexistente_no_deja_generar() -> None:
    class SinSaldo(SaldosFalsos):
        async def saldo_pendiente(self, comprobante_id: UUID) -> Decimal | None:
            del comprobante_id
            return None

    with pytest.raises(CobroInexistente):
        await _generar(CobrosFalsos(), PasarelaFalsa(), SinSaldo()).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            cliente_id=CLIENTE,
            monto=Decimal("100.00"),
            descripcion="Pago",
            ahora=AHORA,
            comprobante_id=uuid4(),
        )


# ------------------------------------------------------------------ regenerar y cancelar


async def test_regenerar_reemplaza_el_link_anterior() -> None:
    """El último criterio de HU-E6-03: invalida el anterior y activa el nuevo."""
    cobros = CobrosFalsos()
    cobro = _cobro()
    await cobros.agregar(cobro)

    class OtraPreferencia(PasarelaFalsa):
        async def crear_link(
            self, *, empresa_id: EmpresaId, cobro: Cobro, url_de_retorno: str
        ) -> LinkDePago:
            del empresa_id, cobro, url_de_retorno
            return LinkDePago(preference_id="pref-2", url="https://mp.com/x2")

    resultado = await RegenerarLink(
        cobros=cobros,
        pasarela=OtraPreferencia(),
        publicador=PublicadorFalso(),
        url_de_retorno=URL_RETORNO,
    ).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        cobro_id=cobro.id,
        ahora=AHORA,
    )

    assert resultado.link is not None
    assert resultado.link.preference_id == "pref-2"


async def test_cancelar_un_pagado_usa_el_texto_de_la_historia() -> None:
    cobros = CobrosFalsos()
    cobro = _cobro()
    cobro.aprobar(payment_id="pago-1", ahora=AHORA)
    await cobros.agregar(cobro)

    pasarela = PasarelaFalsa()
    with pytest.raises(CobroNoCancelable) as exc:
        await _cancelar(cobros, pasarela).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            cobro_id=cobro.id,
            motivo="Ya no corresponde cobrarlo",
            ahora=AHORA,
        )

    assert "reembolso" in str(exc.value).lower()
    # RN-01 se resuelve sin gastar una llamada de red: el agregado corta antes.
    assert pasarela.invalidados == []


def _cancelar(cobros: CobrosFalsos, pasarela: PasarelaFalsa) -> CancelarCobro:
    return CancelarCobro(cobros=cobros, pasarela=pasarela, publicador=PublicadorFalso())


async def test_cancelar_invalida_el_link_en_mercadopago() -> None:
    """HU-E6-04 RN-03. **El caso que faltaba**: sin esto el link seguía cobrando."""
    cobros = CobrosFalsos()
    cobro = _cobro()
    await cobros.agregar(cobro)
    pasarela = PasarelaFalsa()

    resultado = await _cancelar(cobros, pasarela).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        cobro_id=cobro.id,
        motivo="El cliente ya pago por transferencia",
        ahora=AHORA,
    )

    assert resultado.estado is EstadoCobro.CANCELADO
    assert pasarela.invalidados == [UN_LINK.preference_id]


async def test_si_mercadopago_no_invalida_el_cobro_no_se_cancela() -> None:
    """La decisión de esta unidad: una operación sobre plata no se hace a medias.

    Lo que se afirma no es sólo que levante, sino que **no quede nada escrito**: ni el estado
    ni el motivo ni el evento de bitácora. Un cobro cancelado a medias, con el link todavía
    cobrando, es peor que uno que no se pudo cancelar.
    """
    cobros = CobrosFalsos()
    cobro = _cobro()
    await cobros.agregar(cobro)
    publicador = PublicadorFalso()

    caso = CancelarCobro(cobros=cobros, pasarela=PasarelaQueNoInvalida(), publicador=publicador)
    with pytest.raises(PasarelaNoDisponible):
        await caso.ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            cobro_id=cobro.id,
            motivo="El cliente ya pago por transferencia",
            ahora=AHORA,
        )

    # No se escribió nada ni se publicó nada. Se afirma sobre `escrituras` y no sobre el
    # estado del objeto porque este doble guarda la referencia que el caso de uso ya mutó; el
    # repositorio real reconstituye, y eso lo prueba el test de integración contra PostgreSQL.
    assert cobros.escrituras == []
    assert publicador.eventos == []


async def test_cancelar_sin_link_no_llama_a_mercadopago() -> None:
    """Nunca hubo preferencia: no hay nada que invalidar."""
    cobros = CobrosFalsos()
    cobro = Cobro(
        id=uuid4(),
        empresa_id=EMPRESA,
        cliente_id=uuid4(),
        monto=Decimal("1210.00"),
        descripcion="Consulta de septiembre",
        vence_el=AHORA + timedelta(days=30),
        created_at=AHORA,
    )
    await cobros.agregar(cobro)
    pasarela = PasarelaFalsa()

    resultado = await _cancelar(cobros, pasarela).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        cobro_id=cobro.id,
        motivo="Se cargo por duplicado",
        ahora=AHORA,
    )

    assert resultado.estado is EstadoCobro.CANCELADO
    assert pasarela.invalidados == []


async def test_cancelar_un_vencido_no_llama_a_mercadopago() -> None:
    """La preferencia se creó con `expiration_date_to = vence_el`: ya expiró sola.

    El atajo es una equivalencia exacta, no una heurística, y este test es lo que la ata: si
    el adaptador dejara de mandar ese campo, esta afirmación habría que sacarla con él.
    """
    cobros = CobrosFalsos()
    cobro = _cobro()
    despues = cobro.vence_el + timedelta(days=1)
    cobro.vencer(despues)
    await cobros.agregar(cobro)
    pasarela = PasarelaFalsa()

    resultado = await _cancelar(cobros, pasarela).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        cobro_id=cobro.id,
        motivo="Incobrable, se da de baja",
        ahora=despues,
    )

    assert resultado.estado is EstadoCobro.CANCELADO
    assert pasarela.invalidados == []


async def test_un_motivo_corto_no_gasta_una_llamada_a_mercadopago() -> None:
    """RN-02 se valida en el agregado, y el agregado corre primero."""
    cobros = CobrosFalsos()
    cobro = _cobro()
    await cobros.agregar(cobro)
    pasarela = PasarelaFalsa()

    with pytest.raises(EntradaInvalida):
        await _cancelar(cobros, pasarela).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            cobro_id=cobro.id,
            motivo="corto",
            ahora=AHORA,
        )

    assert pasarela.invalidados == []


# ------------------------------------------------------------------ reembolsar · D27


async def test_solo_el_administrador_reembolsa() -> None:
    """HU-E6-05 RN-05: el Operador ve el detalle pero no inicia el reembolso."""
    cobros = CobrosFalsos()
    cobro = _cobro()
    cobro.aprobar(payment_id="pago-1", ahora=AHORA)
    await cobros.agregar(cobro)

    with pytest.raises(EntradaInvalida):
        await ReembolsarCobro(
            cobros=cobros, pasarela=PasarelaFalsa(), publicador=PublicadorFalso()
        ).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            cobro_id=cobro.id,
            monto=Decimal("100.00"),
            ahora=AHORA,
        )


async def test_un_reembolso_aceptado_cierra_el_cobro() -> None:
    cobros = CobrosFalsos()
    cobro = _cobro()
    cobro.aprobar(payment_id="pago-1", ahora=AHORA)
    await cobros.agregar(cobro)

    resultado = await ReembolsarCobro(
        cobros=cobros, pasarela=PasarelaFalsa(), publicador=PublicadorFalso()
    ).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.ADMINISTRADOR,
        cobro_id=cobro.id,
        monto=Decimal("1210.00"),
        ahora=AHORA,
    )

    assert resultado.estado is EstadoCobro.REEMBOLSADO
    assert resultado.monto_reembolsado == Decimal("1210.00")


async def test_un_reembolso_rechazado_deja_el_cobro_pagado() -> None:
    """**Decisión D27.** RN-03: mantiene su estado y se notifica al administrador.

    No hay vuelta atrás que hacer porque el estado nunca se fue: eso es exactamente lo que
    se gana no agregando `REEMBOLSO_EN_PROCESO` al enum.
    """
    cobros = CobrosFalsos()
    cobro = _cobro()
    cobro.aprobar(payment_id="pago-1", ahora=AHORA)
    await cobros.agregar(cobro)

    with pytest.raises(ReembolsoRechazado):
        await ReembolsarCobro(
            cobros=cobros,
            pasarela=PasarelaQueRechazaElReembolso(),
            publicador=PublicadorFalso(),
        ).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.ADMINISTRADOR,
            cobro_id=cobro.id,
            monto=Decimal("1210.00"),
            ahora=AHORA,
        )

    assert cobro.estado is EstadoCobro.APROBADO
    assert not cobro.reembolso_en_proceso
    assert cobro.monto_reembolsado is None


async def test_no_se_reembolsa_lo_que_no_esta_pagado() -> None:
    cobros = CobrosFalsos()
    cobro = _cobro()
    await cobros.agregar(cobro)

    with pytest.raises(CobroNoReembolsable):
        await ReembolsarCobro(
            cobros=cobros, pasarela=PasarelaFalsa(), publicador=PublicadorFalso()
        ).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.ADMINISTRADOR,
            cobro_id=cobro.id,
            monto=Decimal("100.00"),
            ahora=AHORA,
        )


# ------------------------------------------------------------------ consultas


async def test_ver_uno_inexistente_falla_en_vez_de_devolver_nada() -> None:
    with pytest.raises(CobroInexistente):
        await VerCobro(CobrosFalsos()).ejecutar(uuid4())


async def test_las_metricas_arrancan_en_el_mes_en_curso() -> None:
    """RN-01: el período por defecto lo decide el caso de uso, no la pantalla.

    Dejarlo en el frontend haría que el reporte del épico 9 tuviera que redecidirlo.
    """

    class CobrosQueRecuerdan(CobrosFalsos):
        def __init__(self) -> None:
            super().__init__()
            self.filtros_usados: list[FiltrosDeCobro] = []

        async def metricas(self, filtros: FiltrosDeCobro) -> MetricasDeCobros:
            self.filtros_usados.append(filtros)
            return await super().metricas(filtros)

    cobros = CobrosQueRecuerdan()
    await MetricasDelPeriodo(cobros).ejecutar(ahora=AHORA)

    assert cobros.filtros_usados[0].desde == datetime(2026, 9, 1, tzinfo=UTC)


async def test_listar_devuelve_lo_que_el_repositorio_da() -> None:
    cobros = CobrosFalsos()
    await cobros.agregar(_cobro())

    assert len(await ListarCobros(cobros).ejecutar()) == 1


# ------------------------------------------------------------------ vencer · D23


async def test_vencer_mueve_a_los_que_pasaron_su_fecha() -> None:
    """RN-03, y es una transición real y no una propiedad calculada (D23)."""
    cobros = CobrosFalsos()
    vencido = _cobro(vence_en_dias=1)
    vigente = _cobro(vence_en_dias=30)
    await cobros.agregar(vencido)
    await cobros.agregar(vigente)
    despues = AHORA + timedelta(days=2)

    resultado = await VencerCobros(cobros=cobros, publicador=PublicadorFalso()).ejecutar(
        empresa_id=EMPRESA, ahora=despues
    )

    assert resultado.procesados == 1
    assert vencido.estado is EstadoCobro.VENCIDO
    assert vigente.estado is EstadoCobro.PENDIENTE


async def test_vencer_dos_veces_no_rompe() -> None:
    """El barrido corre cada hora: la segunda corrida encuentra lo mismo."""
    cobros = CobrosFalsos()
    cobro = _cobro(vence_en_dias=1)
    await cobros.agregar(cobro)
    despues = AHORA + timedelta(days=2)
    barrido = VencerCobros(cobros=cobros, publicador=PublicadorFalso())

    await barrido.ejecutar(empresa_id=EMPRESA, ahora=despues)
    segunda = await barrido.ejecutar(empresa_id=EMPRESA, ahora=despues)

    assert segunda.procesados == 0


# ------------------------------------------------------------------ recordatorios · D25


def _despachar(
    cobros: CobrosFalsos,
    recordatorios: RecordatoriosFalsos,
    envio: EnvioFalso,
    cadena: CadenaFalsa,
) -> DespacharRecordatorios:
    return DespacharRecordatorios(
        cobros=cobros,
        recordatorios=recordatorios,
        envio=envio,
        cadena=cadena,
        publicador=PublicadorFalso(),
    )


async def test_un_cobro_que_llego_al_umbral_recibe_su_primer_recordatorio() -> None:
    cobros, recordatorios, envio = CobrosFalsos(), RecordatoriosFalsos(), EnvioFalso()
    cobro = _cobro(vence_en_dias=0)
    await cobros.agregar(cobro)
    despues = AHORA + timedelta(days=4)

    resultado = await _despachar(cobros, recordatorios, envio, CadenaFalsa()).ejecutar(
        empresa_id=EMPRESA, ahora=despues
    )

    assert resultado.procesados == 1
    assert envio.enviados == [(cobro.id, 1, "WHATSAPP")]


async def test_un_planificador_atrasado_manda_un_paso_por_corrida() -> None:
    """**Decisión D25**, y el test que la justifica.

    Con tres pasos vencidos, un barrido basado en fechas mandaría los tres de golpe. Uno
    basado en el paso manda el 1, y el 2 en la corrida siguiente — que es lo que un cliente
    espera de una cadena de recordatorios.
    """
    cobros, recordatorios, envio = CobrosFalsos(), RecordatoriosFalsos(), EnvioFalso()
    cobro = _cobro(vence_en_dias=0)
    await cobros.agregar(cobro)
    # Veinte días después del vencimiento: los tres pasos (3, 7, 15) están vencidos.
    despues = AHORA + timedelta(days=20)
    barrido = _despachar(cobros, recordatorios, envio, CadenaFalsa())

    await barrido.ejecutar(empresa_id=EMPRESA, ahora=despues)
    assert [paso for _, paso, _ in envio.enviados] == [1]

    await barrido.ejecutar(empresa_id=EMPRESA, ahora=despues)
    assert [paso for _, paso, _ in envio.enviados] == [1, 2]


async def test_dos_barridos_solapados_no_mandan_el_mismo_paso_dos_veces() -> None:
    """HS-T3 RN-05, defendido por el índice único que el doble simula.

    El dominio calcula cuál falta; el índice atrapa el caso en que dos barridos calcularon lo
    mismo a la vez. Sin la segunda capa, dos workers concurrentes mandan el mismo mensaje.
    """
    cobros, recordatorios, envio = CobrosFalsos(), RecordatoriosFalsos(), EnvioFalso()
    cobro = _cobro(vence_en_dias=0)
    await cobros.agregar(cobro)
    despues = AHORA + timedelta(days=4)

    # El primero deja la fila; el segundo la encuentra ocupada.
    await recordatorios.agregar(
        Recordatorio(id=uuid4(), cobro_id=cobro.id, paso=1, canal="WHATSAPP")
    )

    resultado = await _despachar(cobros, recordatorios, envio, CadenaFalsa()).ejecutar(
        empresa_id=EMPRESA, ahora=despues
    )

    assert resultado.procesados == 0
    assert envio.enviados == []


async def test_un_cobro_pagado_deja_de_recibir_recordatorios() -> None:
    """HS-T3 RN-03. La cadena se corta por el estado, no por una llamada aparte."""
    cobros, recordatorios, envio = CobrosFalsos(), RecordatoriosFalsos(), EnvioFalso()
    cobro = _cobro(vence_en_dias=0)
    cobro.aprobar(payment_id="pago-1", ahora=AHORA)
    await cobros.agregar(cobro)

    resultado = await _despachar(cobros, recordatorios, envio, CadenaFalsa()).ejecutar(
        empresa_id=EMPRESA, ahora=AHORA + timedelta(days=20)
    )

    assert resultado.procesados == 0


async def test_antes_del_umbral_no_sale_nada() -> None:
    cobros, recordatorios, envio = CobrosFalsos(), RecordatoriosFalsos(), EnvioFalso()
    await cobros.agregar(_cobro(vence_en_dias=0))

    resultado = await _despachar(cobros, recordatorios, envio, CadenaFalsa()).ejecutar(
        empresa_id=EMPRESA, ahora=AHORA + timedelta(days=1)
    )

    assert resultado.procesados == 0


async def test_cuando_la_cadena_se_termina_no_pasa_nada() -> None:
    """Hay un tope de pasos a propósito: una deuda impaga después del último recordatorio es
    un problema humano, no uno que se resuelva mandando un mensaje más."""
    cobros, recordatorios, envio = CobrosFalsos(), RecordatoriosFalsos(), EnvioFalso()
    cobro = _cobro(vence_en_dias=0)
    await cobros.agregar(cobro)
    for paso in (1, 2, 3):
        uno = Recordatorio(id=uuid4(), cobro_id=cobro.id, paso=paso, canal="WHATSAPP")
        uno.marcar_enviado(AHORA)
        await recordatorios.agregar(uno)

    resultado = await _despachar(cobros, recordatorios, envio, CadenaFalsa()).ejecutar(
        empresa_id=EMPRESA, ahora=AHORA + timedelta(days=60)
    )

    assert resultado.procesados == 0
