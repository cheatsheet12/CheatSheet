"""Los reembolsos (HU-E6-05): dos transacciones, una clave de idempotencia y filas inmutables.

Lo que se juega acá es plata que sale de la cuenta de una empresa. Tres cosas se prueban con
todas las letras:

- **H1** — la solicitud (con su clave) queda escrita **antes** de hablar con MercadoPago, y el
  rechazo o la falta de respuesta también quedan escritos. El caso de uso no levanta: devuelve
  el resultado y el borde re-levanta **después** del commit (`tests/api/test_reembolso_confirma_el_estado.py`).
- **La clave se reusa**: un reintento manda la misma `X-Idempotency-Key`, nunca una nueva.
- **Una confirmación, un efecto**: «Actualizar estado» dos veces inserta una sola fila.

Los dobles del webhook (`CobrosFalsos`, `PasarelaFalsa`, `SaldosFalsos`, `PublicadorFalso`) se
reusan: son los mismos puertos, y dos juegos para los mismos protocolos serían dos cosas que
pueden discrepar.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.payments.application.cobros import MOTIVO_SOLO_ADMIN_REEMBOLSA
from cheatsheet.contexts.payments.application.errors import (
    CobroInexistente,
    CobroNoReembolsable,
    PasarelaNoDisponible,
    ReembolsoEnProceso,
    ReembolsoNoCorregible,
)
from cheatsheet.contexts.payments.application.ports import (
    EstadoDeReembolso,
    RespuestaDeReembolso,
)
from cheatsheet.contexts.payments.application.reembolsos import (
    ActualizarReembolso,
    EnviarReembolso,
    ResultadoDeReembolso,
    SolicitarReembolso,
)
from cheatsheet.contexts.payments.application.reembolsos_manuales import (
    CorregirReembolso,
    RegistrarReembolsoManual,
    VerReembolsos,
)
from cheatsheet.contexts.payments.domain.cobro import (
    MENSAJE_REEMBOLSO_EXCEDIDO,
    Cobro,
    EstadoCobro,
    LinkDePago,
    MedioDePago,
)
from cheatsheet.contexts.payments.domain.reembolso import OrigenDeReembolso, Reembolso
from cheatsheet.shared.auditoria import EventoAuditable, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, OperacionNoPermitida
from cheatsheet.shared.roles import RolUsuario

from tests.contexts.payments.application.test_confirmacion import (
    CobrosFalsos,
    PasarelaFalsa,
    PublicadorFalso,
    SaldosFalsos,
)

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
USUARIO = UsuarioId(uuid4())
ADMIN = RolUsuario.ADMINISTRADOR
UN_LINK = LinkDePago(preference_id="pref-1", url="https://mp.com/checkout/pref-1")
COMPROBANTE = uuid4()


class ReembolsosFalsos:
    """`PortRepositorioReembolso` en memoria. La unicidad de `mp_refund_id` vive en la base."""

    def __init__(self) -> None:
        self.filas: list[Reembolso] = []

    async def agregar(self, reembolso: Reembolso) -> None:
        self.filas.append(reembolso)

    async def de_cobro(self, cobro_id: UUID) -> list[Reembolso]:
        return [f for f in self.filas if f.cobro_id == cobro_id]

    async def buscar_por_id(self, reembolso_id: UUID) -> Reembolso | None:
        return next((f for f in self.filas if f.id == reembolso_id), None)


class Mundo:
    """Todo lo que un caso de uso de reembolso toca, junto."""

    def __init__(self, *, comprobante: UUID | None = None, transferencia: bool = False) -> None:
        self.cobros = CobrosFalsos()
        self.reembolsos = ReembolsosFalsos()
        self.pasarela = PasarelaFalsa()
        self.saldos = SaldosFalsos(Decimal("0.00"))
        self.publicador = PublicadorFalso()
        self.cobro = Cobro(
            id=uuid4(),
            empresa_id=EMPRESA,
            cliente_id=uuid4(),
            monto=Decimal("1000.00"),
            descripcion="Consulta de septiembre",
            vence_el=AHORA + timedelta(days=30),
            created_at=AHORA - timedelta(days=3),
            comprobante_id=comprobante,
            medio_de_pago=(
                MedioDePago.TRANSFERENCIA if transferencia else MedioDePago.LINK_MERCADOPAGO
            ),
        )
        self.cobro.asignar_link(UN_LINK, AHORA - timedelta(days=3))
        self.cobro.aprobar(payment_id="pago-1", ahora=AHORA - timedelta(days=1))
        self.cobros.guardados[self.cobro.id] = self.cobro

    def solicitar(self) -> SolicitarReembolso:
        return SolicitarReembolso(cobros=self.cobros, publicador=self.publicador)

    def enviar(self) -> EnviarReembolso:
        return EnviarReembolso(
            cobros=self.cobros,
            reembolsos=self.reembolsos,
            pasarela=self.pasarela,
            saldos=self.saldos,
            publicador=self.publicador,
        )

    def actualizar(self) -> ActualizarReembolso:
        return ActualizarReembolso(
            cobros=self.cobros,
            reembolsos=self.reembolsos,
            pasarela=self.pasarela,
            saldos=self.saldos,
            publicador=self.publicador,
        )

    def manual(self) -> RegistrarReembolsoManual:
        return RegistrarReembolsoManual(
            cobros=self.cobros,
            reembolsos=self.reembolsos,
            saldos=self.saldos,
            publicador=self.publicador,
        )

    def corregir(self) -> CorregirReembolso:
        return CorregirReembolso(
            cobros=self.cobros,
            reembolsos=self.reembolsos,
            saldos=self.saldos,
            publicador=self.publicador,
        )

    async def pedir(self, monto: str = "400.00", *, rol: RolUsuario = ADMIN) -> Cobro:
        return await self.solicitar().ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=rol,
            cobro_id=self.cobro.id,
            monto=Decimal(monto),
            ahora=AHORA,
        )

    async def enviar_ahora(self, *, rol: RolUsuario = ADMIN) -> ResultadoDeReembolso:
        return await self.enviar().ejecutar(
            empresa_id=EMPRESA, usuario_id=USUARIO, rol=rol, cobro_id=self.cobro.id, ahora=AHORA
        )

    async def actualizar_ahora(self, *, rol: RolUsuario = ADMIN) -> ResultadoDeReembolso:
        return await self.actualizar().ejecutar(
            empresa_id=EMPRESA, usuario_id=USUARIO, rol=rol, cobro_id=self.cobro.id, ahora=AHORA
        )

    async def registrar_manual(
        self, monto: str = "300.00", *, rol: RolUsuario = ADMIN, motivo: str = "Devolucion"
    ) -> Cobro:
        return await self.manual().ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=rol,
            cobro_id=self.cobro.id,
            monto=Decimal(monto),
            dia=date(2026, 9, 7),
            referencia="OP-9",
            motivo=motivo,
            ahora=AHORA,
        )

    def eventos(self, accion: str) -> list[EventoAuditable]:
        return [
            e
            for e in self.publicador.eventos
            if isinstance(e, EventoAuditable) and e.accion == accion
        ]


def _estado(cobro: Cobro) -> EstadoCobro:
    """Lectura a través de una función: evita el narrowing de mypy entre dos mutaciones."""
    return cobro.estado


# ------------------------------------------------------------------ RN-05: solo el Administrador


@pytest.mark.parametrize("rol", [RolUsuario.OPERADOR, RolUsuario.SOLO_LECTURA])
async def test_solo_el_administrador_solicita_actualiza_registra_y_corrige(
    rol: RolUsuario,
) -> None:
    """Caso 17. El guarda vive en el caso de uso, no solo en el router (PRU-09)."""
    mundo = Mundo(transferencia=True)
    una_fila = Reembolso(
        id=uuid4(),
        empresa_id=EMPRESA,
        cobro_id=mundo.cobro.id,
        monto=Decimal("10.00"),
        fecha_devolucion=AHORA,
        origen=OrigenDeReembolso.MANUAL,
        created_at=AHORA,
        motivo="x",
    )
    mundo.reembolsos.filas.append(una_fila)

    intentos = (
        mundo.pedir(rol=rol),
        mundo.enviar_ahora(rol=rol),
        mundo.actualizar_ahora(rol=rol),
        mundo.registrar_manual(rol=rol),
        mundo.corregir().ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=rol,
            cobro_id=mundo.cobro.id,
            reembolso_id=una_fila.id,
            motivo="Se cargo por error",
            ahora=AHORA,
        ),
    )
    for intento in intentos:
        with pytest.raises(OperacionNoPermitida) as exc:
            await intento
        assert str(exc.value) == MOTIVO_SOLO_ADMIN_REEMBOLSA

    assert mundo.cobros.escrituras == []
    assert mundo.pasarela.reembolsos_pedidos == []


# ------------------------------------------------------------------ T1: la solicitud


async def test_solicitar_persiste_monto_y_clave_sin_hablar_con_mercadopago() -> None:
    """Caso 10. T1 escribe la marca de «en proceso» y la clave de idempotencia, y nada más."""
    mundo = Mundo()

    cobro = await mundo.pedir("400.00")

    assert cobro.reembolso_en_proceso
    assert cobro.reembolso_solicitado_monto == Decimal("400.00")
    assert cobro.reembolso_clave_idempotencia is not None
    assert _estado(cobro) is EstadoCobro.APROBADO
    assert mundo.cobros.escrituras == [cobro.id]
    assert mundo.cobros.bloqueados == [cobro.id]
    assert mundo.pasarela.reembolsos_pedidos == []
    assert [e.accion for e in mundo.publicador.eventos if isinstance(e, EventoAuditable)] == [
        "solicitar_reembolso"
    ]


async def test_la_pasarela_ve_el_cobro_ya_marcado_cuando_T2_la_llama() -> None:
    """Caso 10: lo que llega a MercadoPago es lo que T1 dejó escrito, con **su** clave."""
    mundo = Mundo()
    cobro = await mundo.pedir("400.00")
    clave = cobro.reembolso_clave_idempotencia

    class PasarelaQueMiraElCobro(PasarelaFalsa):
        visto: tuple[bool, UUID | None] = (False, None)

        async def reembolsar(
            self, *, empresa_id: EmpresaId, payment_id: str, monto: Decimal, clave: UUID
        ) -> RespuestaDeReembolso:
            persistido = mundo.cobros.guardados[mundo.cobro.id]
            self.visto = (persistido.reembolso_en_proceso, persistido.reembolso_clave_idempotencia)
            return await super().reembolsar(
                empresa_id=empresa_id, payment_id=payment_id, monto=monto, clave=clave
            )

    espia = PasarelaQueMiraElCobro()
    mundo.pasarela = espia
    await mundo.enviar_ahora()

    assert espia.visto == (True, clave)
    assert espia.reembolsos_pedidos == [("pago-1", Decimal("400.00"), clave)]


async def test_no_se_solicita_sobre_lo_que_no_admite_reembolso() -> None:
    """Caso 3 y 5 a nivel de aplicación: 409 con el texto de la historia."""
    transferencia = Mundo(transferencia=True)
    pendiente = Mundo()
    pendiente.cobro.estado = EstadoCobro.PENDIENTE

    for mundo in (transferencia, pendiente):
        with pytest.raises(CobroNoReembolsable):
            await mundo.pedir()
        assert mundo.cobros.escrituras == []


async def test_con_un_reembolso_en_vuelo_no_se_solicita_otro() -> None:
    """Caso 4: la solicitud en vuelo es el mutex; el segundo recibe un 409 propio."""
    mundo = Mundo()
    primero = await mundo.pedir("100.00")
    clave = primero.reembolso_clave_idempotencia

    with pytest.raises(ReembolsoEnProceso):
        await mundo.pedir("100.00")

    assert mundo.cobro.reembolso_clave_idempotencia == clave


async def test_un_monto_mayor_al_pendiente_es_un_422_sin_escribir_nada() -> None:
    mundo = Mundo()

    with pytest.raises(EntradaInvalida) as exc:
        await mundo.pedir("1000.01")

    assert str(exc.value) == MENSAJE_REEMBOLSO_EXCEDIDO
    assert mundo.cobros.escrituras == []


async def test_un_cobro_ajeno_o_inexistente_es_el_mismo_error() -> None:
    mundo = Mundo()

    with pytest.raises(CobroInexistente):
        await mundo.solicitar().ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=ADMIN,
            cobro_id=uuid4(),
            monto=Decimal("1.00"),
            ahora=AHORA,
        )


# ------------------------------------------------------------------ T2: la respuesta de MercadoPago


async def test_un_reembolso_aceptado_registra_fila_acumulado_estado_y_bitacora() -> None:
    """Caso 13 (aceptado): una fila `API_MERCADOPAGO` con el id y la fecha de MercadoPago."""
    mundo = Mundo()
    await mundo.pedir("400.00")
    fecha = AHORA - timedelta(minutes=5)
    mundo.pasarela.respuesta_de_reembolso = RespuestaDeReembolso(
        estado=EstadoDeReembolso.ACEPTADO,
        mp_refund_id="ref-77",
        monto=Decimal("400.00"),
        fecha=fecha,
    )

    resultado = await mundo.enviar_ahora()

    assert resultado.rechazo is None
    assert _estado(resultado.cobro) is EstadoCobro.REEMBOLSADO_PARCIAL
    assert resultado.cobro.monto_reembolsado == Decimal("400.00")
    assert not resultado.cobro.reembolso_en_proceso
    [fila] = mundo.reembolsos.filas
    assert fila.origen is OrigenDeReembolso.API_MERCADOPAGO
    assert fila.mp_refund_id == "ref-77"
    assert fila.fecha_devolucion == fecha
    assert fila.registrado_por is None
    [evento] = mundo.eventos("confirmar_reembolso")
    assert evento.resultado is Resultado.COMPLETADO
    assert evento.usuario_id == USUARIO
    assert evento.detalle is not None
    assert evento.detalle["monto"] == "400.00"
    assert evento.detalle["origen"] == "API_MERCADOPAGO"
    assert evento.detalle["reembolso_id"] == str(fila.id)


async def test_sin_monto_en_la_respuesta_se_confirma_lo_solicitado() -> None:
    mundo = Mundo()
    await mundo.pedir("250.00")

    resultado = await mundo.enviar_ahora()

    assert resultado.cobro.monto_reembolsado == Decimal("250.00")


async def test_completar_el_monto_deja_el_cobro_reembolsado() -> None:
    mundo = Mundo()
    await mundo.pedir("400.00")
    await mundo.enviar_ahora()
    await mundo.pedir("600.00")

    resultado = await mundo.enviar_ahora()

    assert _estado(resultado.cobro) is EstadoCobro.REEMBOLSADO
    assert len(mundo.reembolsos.filas) == 2


async def test_un_rechazo_queda_escrito_y_se_devuelve_para_levantarlo_despues() -> None:
    """Caso 11 (H1): el caso de uso **no levanta**; escribe el rechazo y el evento `ERROR` y
    devuelve el motivo, para que el borde levante después del commit."""
    mundo = Mundo()
    await mundo.pedir("400.00")
    mundo.pasarela.respuesta_de_reembolso = RespuestaDeReembolso(
        estado=EstadoDeReembolso.RECHAZADO, motivo="Refund not supported (4295)"
    )
    escrituras = len(mundo.cobros.escrituras)

    resultado = await mundo.enviar_ahora()

    assert resultado.rechazo == "Refund not supported (4295)"
    assert not resultado.cobro.reembolso_en_proceso
    assert _estado(resultado.cobro) is EstadoCobro.APROBADO
    assert resultado.cobro.monto_reembolsado == Decimal("0.00")
    assert len(mundo.cobros.escrituras) == escrituras + 1
    assert mundo.reembolsos.filas == []
    [evento] = mundo.eventos("rechazar_reembolso")
    assert evento.resultado is Resultado.ERROR
    assert evento.detalle is not None
    assert evento.detalle["motivo_mercadopago"] == "Refund not supported (4295)"


async def test_sin_respuesta_de_mercadopago_la_solicitud_queda_en_vuelo_y_avisa() -> None:
    """Caso 12 (H1): la plata puede haber salido, así que no se pierde la marca ni la clave."""
    mundo = Mundo()
    pedido = await mundo.pedir("400.00")
    clave = pedido.reembolso_clave_idempotencia
    mundo.pasarela.respuesta_de_reembolso = PasarelaNoDisponible("MercadoPago no respondio")

    resultado = await mundo.enviar_ahora()

    assert resultado.rechazo is None
    assert resultado.cobro.reembolso_en_proceso
    assert resultado.cobro.reembolso_clave_idempotencia == clave
    assert mundo.reembolsos.filas == []
    [evento] = mundo.eventos("reembolso_sin_confirmar")
    assert evento.resultado is Resultado.ERROR


async def test_un_reembolso_en_proceso_guarda_el_id_y_no_crea_fila() -> None:
    """Caso 13 (`en_proceso`): sin fila, en vuelo, con el id para consultarlo después."""
    mundo = Mundo()
    await mundo.pedir("400.00")
    mundo.pasarela.respuesta_de_reembolso = RespuestaDeReembolso(
        estado=EstadoDeReembolso.EN_PROCESO, mp_refund_id="ref-5"
    )

    resultado = await mundo.enviar_ahora()

    assert resultado.cobro.reembolso_en_proceso
    assert resultado.cobro.reembolso_mp_refund_id == "ref-5"
    assert mundo.reembolsos.filas == []
    [evento] = mundo.eventos("reembolso_sin_confirmar")
    assert evento.resultado is Resultado.COMPLETADO


async def test_una_confirmacion_mayor_al_pendiente_no_se_registra_y_avisa() -> None:
    """Caso 15: queda en vuelo con el id, no hay fila y el evento es `ERROR`."""
    mundo = Mundo()
    await mundo.pedir("400.00")
    mundo.pasarela.respuesta_de_reembolso = RespuestaDeReembolso(
        estado=EstadoDeReembolso.ACEPTADO, mp_refund_id="ref-9", monto=Decimal("1500.00")
    )

    resultado = await mundo.enviar_ahora()

    assert resultado.cobro.reembolso_en_proceso
    assert resultado.cobro.monto_reembolsado == Decimal("0.00")
    assert mundo.reembolsos.filas == []
    [evento] = mundo.eventos("reembolso_sin_confirmar")
    assert evento.resultado is Resultado.ERROR


async def test_enviar_sin_solicitud_en_vuelo_no_hace_nada() -> None:
    mundo = Mundo()

    resultado = await mundo.enviar_ahora()

    assert resultado.cobro is mundo.cobro
    assert mundo.pasarela.reembolsos_pedidos == []
    assert mundo.publicador.eventos == []


# ------------------------------------------------------------------ Actualizar estado


async def test_actualizar_con_id_consulta_y_no_reenvia() -> None:
    """Caso 14: con el id de MercadoPago se consulta; el POST no se repite."""
    mundo = Mundo()
    await mundo.pedir("400.00")
    mundo.pasarela.respuesta_de_reembolso = RespuestaDeReembolso(
        estado=EstadoDeReembolso.EN_PROCESO, mp_refund_id="ref-5"
    )
    await mundo.enviar_ahora()
    pedidos = len(mundo.pasarela.reembolsos_pedidos)
    mundo.pasarela.respuesta_de_consulta = RespuestaDeReembolso(
        estado=EstadoDeReembolso.ACEPTADO, mp_refund_id="ref-5", monto=Decimal("400.00")
    )

    resultado = await mundo.actualizar_ahora()

    assert mundo.pasarela.reembolsos_consultados == ["ref-5"]
    assert len(mundo.pasarela.reembolsos_pedidos) == pedidos
    assert _estado(resultado.cobro) is EstadoCobro.REEMBOLSADO_PARCIAL
    assert [f.mp_refund_id for f in mundo.reembolsos.filas] == ["ref-5"]


async def test_actualizar_sin_id_reenvia_con_la_misma_clave() -> None:
    """Caso 14, la razón de existir de la clave persistida: el reintento no duplica."""
    mundo = Mundo()
    pedido = await mundo.pedir("400.00")
    clave = pedido.reembolso_clave_idempotencia
    mundo.pasarela.respuesta_de_reembolso = PasarelaNoDisponible("MercadoPago no respondio")
    await mundo.enviar_ahora()
    mundo.pasarela.respuesta_de_reembolso = RespuestaDeReembolso(
        estado=EstadoDeReembolso.ACEPTADO, mp_refund_id="ref-1"
    )

    resultado = await mundo.actualizar_ahora()

    claves = [c for _, _, c in mundo.pasarela.reembolsos_pedidos]
    assert claves == [clave, clave]
    assert mundo.pasarela.reembolsos_consultados == []
    assert _estado(resultado.cobro) is EstadoCobro.REEMBOLSADO_PARCIAL


async def test_actualizar_dos_veces_seguidas_inserta_una_sola_fila() -> None:
    """Caso 14: la segunda no encuentra nada en vuelo y no llama a nadie."""
    mundo = Mundo()
    await mundo.pedir("400.00")
    mundo.pasarela.respuesta_de_reembolso = PasarelaNoDisponible("MercadoPago no respondio")
    await mundo.enviar_ahora()
    mundo.pasarela.respuesta_de_reembolso = RespuestaDeReembolso(
        estado=EstadoDeReembolso.ACEPTADO, mp_refund_id="ref-1"
    )

    await mundo.actualizar_ahora()
    llamadas = len(mundo.pasarela.reembolsos_pedidos)
    segunda = await mundo.actualizar_ahora()

    assert len(mundo.reembolsos.filas) == 1
    assert len(mundo.pasarela.reembolsos_pedidos) == llamadas
    assert mundo.pasarela.reembolsos_consultados == []
    assert segunda.rechazo is None
    assert segunda.cobro.monto_reembolsado == Decimal("400.00")


async def test_actualizar_puede_terminar_en_rechazo_y_libera_el_cobro() -> None:
    mundo = Mundo()
    await mundo.pedir("400.00")
    mundo.pasarela.respuesta_de_reembolso = RespuestaDeReembolso(
        estado=EstadoDeReembolso.EN_PROCESO, mp_refund_id="ref-5"
    )
    await mundo.enviar_ahora()
    mundo.pasarela.respuesta_de_consulta = RespuestaDeReembolso(
        estado=EstadoDeReembolso.RECHAZADO, motivo="cancelled"
    )

    resultado = await mundo.actualizar_ahora()

    assert resultado.rechazo == "cancelled"
    assert not resultado.cobro.reembolso_en_proceso


# ------------------------------------------------------------------ el saldo del comprobante


async def test_el_reembolso_sube_el_saldo_del_comprobante() -> None:
    """Caso 16: una llamada directa al puerto, en la misma transacción que la fila (P10)."""
    mundo = Mundo(comprobante=COMPROBANTE)
    await mundo.pedir("400.00")

    await mundo.enviar_ahora()

    assert mundo.saldos.devoluciones == [(COMPROBANTE, Decimal("400.00"))]


async def test_sin_comprobante_no_se_toca_ningun_saldo() -> None:
    mundo = Mundo()
    await mundo.pedir("400.00")

    await mundo.enviar_ahora()

    assert mundo.saldos.devoluciones == []


# ------------------------------------------------------------------ el registro manual


async def test_un_reembolso_manual_registra_fila_acumulado_saldo_y_bitacora() -> None:
    mundo = Mundo(comprobante=COMPROBANTE, transferencia=True)

    cobro = await mundo.registrar_manual("300.00")

    assert _estado(cobro) is EstadoCobro.REEMBOLSADO_PARCIAL
    assert cobro.monto_reembolsado == Decimal("300.00")
    [fila] = mundo.reembolsos.filas
    assert fila.origen is OrigenDeReembolso.MANUAL
    assert fila.registrado_por == USUARIO
    assert fila.referencia == "OP-9"
    assert fila.fecha_devolucion == datetime(2026, 9, 7, 15, 0, tzinfo=UTC)
    assert mundo.saldos.devoluciones == [(COMPROBANTE, Decimal("300.00"))]
    assert mundo.cobros.bloqueados == [cobro.id]
    [evento] = mundo.eventos("registrar_reembolso_manual")
    assert evento.resultado is Resultado.COMPLETADO
    # La referencia bancaria es de una persona y **nunca** va a la bitácora.
    assert evento.detalle is not None
    assert "OP-9" not in " ".join(evento.detalle.values())


async def test_un_reembolso_manual_sobre_un_link_es_un_conflicto() -> None:
    mundo = Mundo()

    with pytest.raises(CobroNoReembolsable):
        await mundo.registrar_manual()

    assert mundo.reembolsos.filas == []
    assert mundo.cobros.escrituras == []


async def test_un_reembolso_manual_mayor_al_pendiente_es_un_422() -> None:
    mundo = Mundo(transferencia=True)

    with pytest.raises(EntradaInvalida) as exc:
        await mundo.registrar_manual("1000.01")

    assert str(exc.value) == MENSAJE_REEMBOLSO_EXCEDIDO
    assert mundo.reembolsos.filas == []


# ------------------------------------------------------------------ la corrección


async def _corregir(mundo: Mundo, fila: Reembolso, motivo: str = "Se cargo por error") -> Cobro:
    return await mundo.corregir().ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=ADMIN,
        cobro_id=mundo.cobro.id,
        reembolso_id=fila.id,
        motivo=motivo,
        ahora=AHORA,
    )


async def test_corregir_agrega_una_fila_negativa_y_baja_saldo_y_estado() -> None:
    """Caso 16 (piso) y 7: el saldo vuelve a bajar y el estado se recalcula del acumulado."""
    mundo = Mundo(comprobante=COMPROBANTE, transferencia=True)
    await mundo.registrar_manual("300.00")
    [original] = mundo.reembolsos.filas

    cobro = await _corregir(mundo, original)

    assert _estado(cobro) is EstadoCobro.APROBADO
    assert cobro.monto_reembolsado == Decimal("0.00")
    assert [f.monto for f in mundo.reembolsos.filas] == [Decimal("300.00"), Decimal("-300.00")]
    assert mundo.reembolsos.filas[1].corrige_a == original.id
    assert mundo.saldos.devoluciones[-1] == (COMPROBANTE, Decimal("-300.00"))
    [evento] = mundo.eventos("corregir_reembolso")
    assert evento.resultado is Resultado.COMPLETADO


async def test_no_se_corrige_dos_veces_ni_una_correccion_ni_una_fila_de_la_api() -> None:
    mundo = Mundo(transferencia=True)
    await mundo.registrar_manual("300.00")
    [original] = mundo.reembolsos.filas
    await _corregir(mundo, original)
    correccion = mundo.reembolsos.filas[1]
    de_la_api = Reembolso(
        id=uuid4(),
        empresa_id=EMPRESA,
        cobro_id=mundo.cobro.id,
        monto=Decimal("5.00"),
        fecha_devolucion=AHORA,
        origen=OrigenDeReembolso.API_MERCADOPAGO,
        created_at=AHORA,
    )
    mundo.reembolsos.filas.append(de_la_api)
    filas = len(mundo.reembolsos.filas)

    for fila in (original, correccion, de_la_api):
        with pytest.raises(ReembolsoNoCorregible):
            await _corregir(mundo, fila)

    assert len(mundo.reembolsos.filas) == filas


async def test_corregir_una_fila_de_otro_cobro_o_inexistente_no_existe() -> None:
    mundo = Mundo(transferencia=True)
    ajena = Reembolso(
        id=uuid4(),
        empresa_id=EMPRESA,
        cobro_id=uuid4(),
        monto=Decimal("5.00"),
        fecha_devolucion=AHORA,
        origen=OrigenDeReembolso.MANUAL,
        created_at=AHORA,
        motivo="x",
    )
    mundo.reembolsos.filas.append(ajena)

    with pytest.raises(CobroInexistente):
        await _corregir(mundo, ajena)
    with pytest.raises(CobroInexistente):
        await mundo.corregir().ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=ADMIN,
            cobro_id=mundo.cobro.id,
            reembolso_id=uuid4(),
            motivo="Se cargo por error",
            ahora=AHORA,
        )


# ------------------------------------------------------------------ el historial y los barridos


async def test_ver_reembolsos_devuelve_el_historial_del_cobro() -> None:
    mundo = Mundo(transferencia=True)
    await mundo.registrar_manual("100.00")
    await mundo.registrar_manual("200.00")

    filas = await VerReembolsos(mundo.reembolsos).ejecutar(mundo.cobro.id)

    assert [f.monto for f in filas] == [Decimal("100.00"), Decimal("200.00")]


async def test_un_cobro_reembolsado_no_entra_al_barrido_de_recordatorios() -> None:
    """Caso 18 (RN-12 y D93): por construcción, porque no está abierto."""
    mundo = Mundo()
    await mundo.pedir("400.00")
    await mundo.enviar_ahora()

    assert await mundo.cobros.abiertos() == []
    assert not mundo.cobro.recibe_recordatorios


async def test_un_cobro_en_vuelo_sin_pago_de_mercadopago_es_un_conflicto() -> None:
    """Un `APROBADO` siempre tiene `mp_payment_id`; si no lo tuviera, no se le pregunta nada a
    MercadoPago sobre un pago que no existe."""
    mundo = Mundo()
    await mundo.pedir("400.00")
    mundo.cobro.mp_payment_id = None

    with pytest.raises(CobroNoReembolsable):
        await mundo.enviar_ahora()

    assert mundo.pasarela.reembolsos_pedidos == []
