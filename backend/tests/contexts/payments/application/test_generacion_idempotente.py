"""`GenerarCobro` con clave de idempotencia del pedido (ADR-0013, casos 2 a 7 del plan).

El mismo pedido repetido devuelve el cobro original **sin** volver a MercadoPago ni a la
bitácora; la misma clave con otros datos se rechaza; y la búsqueda de la clave va después del rol
y **antes** de validar el cliente.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.payments.application.cobros import MOTIVO_SIN_PERMISO
from cheatsheet.contexts.payments.application.errors import (
    ClaveDeIdempotenciaReusada,
    PasarelaNoDisponible,
)
from cheatsheet.contexts.payments.application.generacion_de_cobro import (
    MENSAJE_CLAVE_REUSADA,
    GenerarCobro,
)
from cheatsheet.contexts.payments.domain.cobro import Cobro, LinkDePago
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import OperacionNoPermitida
from cheatsheet.shared.roles import RolUsuario

from tests.contexts.payments.application.test_confirmacion import (
    CLIENTE,
    ClientesFalsos,
    CobrosFalsos,
    PasarelaFalsa,
    PublicadorFalso,
    SaldosFalsos,
)

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
USUARIO = UsuarioId(uuid4())
CLAVE = uuid4()


class PasarelaQueFallaUnaVez(PasarelaFalsa):
    """MercadoPago no responde la primera vez y responde la segunda."""

    async def crear_link(
        self, *, empresa_id: EmpresaId, cobro: Cobro, url_de_retorno: str
    ) -> LinkDePago:
        if self.creados == 0:
            self.creados += 1
            raise PasarelaNoDisponible("MercadoPago no respondio")
        return await super().crear_link(
            empresa_id=empresa_id, cobro=cobro, url_de_retorno=url_de_retorno
        )


class Escenario:
    """Los dobles de un caso de uso, para repetir el pedido contra los mismos."""

    def __init__(
        self, *, pasarela: PasarelaFalsa | None = None, clientes: ClientesFalsos | None = None
    ) -> None:
        self.cobros = CobrosFalsos()
        self.pasarela = pasarela or PasarelaFalsa()
        self.clientes = clientes or ClientesFalsos(CLIENTE)
        self.publicador = PublicadorFalso()

    async def pedir(
        self,
        *,
        clave: UUID = CLAVE,
        cliente_id: UUID = CLIENTE,
        monto: str = "1210.01",
        descripcion: str = "Consulta de septiembre",
        comprobante_id: UUID | None = None,
        rol: RolUsuario = RolUsuario.OPERADOR,
    ) -> Cobro:
        return await GenerarCobro(
            cobros=self.cobros,
            pasarela=self.pasarela,
            saldos=SaldosFalsos(cliente=CLIENTE),
            clientes=self.clientes,
            publicador=self.publicador,
            url_de_retorno="https://panel.cheatsheet.ar/cobros",
        ).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=rol,
            clave_idempotencia=clave,
            cliente_id=cliente_id,
            monto=Decimal(monto),
            descripcion=descripcion,
            ahora=AHORA,
            comprobante_id=comprobante_id,
        )


async def test_una_clave_nueva_crea_el_cobro_con_la_clave_y_llama_una_vez_a_la_pasarela() -> None:
    escenario = Escenario()

    cobro = await escenario.pedir()

    assert cobro.clave_idempotencia == CLAVE
    assert escenario.pasarela.creados == 1
    assert escenario.cobros.claves_consultadas == [CLAVE]
    assert len(escenario.publicador.eventos) == 1


async def test_el_mismo_pedido_repetido_devuelve_el_mismo_cobro_sin_tocar_nada() -> None:
    escenario = Escenario()
    primero = await escenario.pedir()

    segundo = await escenario.pedir()

    assert segundo.id == primero.id
    assert escenario.pasarela.creados == 1
    assert len(escenario.cobros.guardados) == 1
    assert len(escenario.publicador.eventos) == 1


async def test_el_monto_repetido_se_compara_redondeado() -> None:
    escenario = Escenario()
    primero = await escenario.pedir(monto="1210.01")

    segundo = await escenario.pedir(monto="1210.005")

    assert segundo.id == primero.id
    assert escenario.pasarela.creados == 1


@pytest.mark.parametrize(
    "cambio",
    [
        {"monto": "1210.02"},
        {"cliente_id": uuid4()},
        {"descripcion": "Otro concepto"},
        {"comprobante_id": uuid4()},
    ],
    ids=["monto", "cliente", "concepto", "comprobante"],
)
async def test_la_misma_clave_con_otros_datos_se_rechaza_sin_pasarela_ni_persistencia(
    cambio: dict[str, object],
) -> None:
    escenario = Escenario()
    escenario.clientes = ClientesFalsos(
        CLIENTE, *(v for v in cambio.values() if isinstance(v, UUID))
    )
    await escenario.pedir()

    with pytest.raises(ClaveDeIdempotenciaReusada) as exc:
        await escenario.pedir(**cambio)  # type: ignore[arg-type]

    assert str(exc.value) == MENSAJE_CLAVE_REUSADA
    assert escenario.pasarela.creados == 1
    assert len(escenario.cobros.guardados) == 1
    assert len(escenario.publicador.eventos) == 1


async def test_la_repeticion_con_el_cliente_ya_inactivo_devuelve_el_cobro_original() -> None:
    """La búsqueda va antes de validar el cliente: el reintento no puede dar un 422."""
    escenario = Escenario()
    primero = await escenario.pedir()
    escenario.clientes.activos.clear()

    segundo = await escenario.pedir()

    assert segundo.id == primero.id


async def test_solo_lectura_se_rechaza_antes_de_buscar_la_clave() -> None:
    escenario = Escenario()

    with pytest.raises(OperacionNoPermitida) as exc:
        await escenario.pedir(rol=RolUsuario.SOLO_LECTURA)

    assert str(exc.value) == MOTIVO_SIN_PERMISO
    assert escenario.cobros.claves_consultadas == []


async def test_si_la_pasarela_falla_nada_queda_guardado_y_la_clave_sirve_de_nuevo() -> None:
    escenario = Escenario(pasarela=PasarelaQueFallaUnaVez())

    with pytest.raises(PasarelaNoDisponible):
        await escenario.pedir()
    assert escenario.cobros.guardados == {}

    cobro = await escenario.pedir()

    assert cobro.clave_idempotencia == CLAVE
    assert len(escenario.cobros.guardados) == 1
