"""HU-E5-05: los puntos de venta, y la numeración que no puede repetirse.

Dos cosas se prueban acá y una tercera **no se puede** probar acá, lo cual también importa
decirlo: la serialización de D14 es del motor y vive en
`tests/integracion/test_puntos_de_venta_postgres.py`. Un test con dobles que «probara» la
concurrencia estaría probando el doble.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.billing.application.errors import (
    ArcaNoDisponible,
    PuntoDeVentaInexistente,
    PuntoDeVentaNoHabilitado,
)
from cheatsheet.contexts.billing.application.ports import PuntoHabilitado
from cheatsheet.contexts.billing.application.puntos_de_venta import (
    MENSAJE_NO_HABILITADO,
    CambiarEstadoDePuntoDeVenta,
    DatosDePuntoDeVenta,
    ListarPuntosDeVenta,
    RegistrarPuntoDeVenta,
)
from cheatsheet.contexts.billing.domain.punto_de_venta import PuntoDeVenta, TipoComprobante
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import InvarianteViolada, OperacionNoPermitida
from cheatsheet.shared.events import EventoDeDominio
from cheatsheet.shared.roles import RolUsuario

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
USUARIO = UsuarioId(uuid4())


class PuntosFalsos:
    def __init__(self) -> None:
        self.guardados: dict[UUID, PuntoDeVenta] = {}

    async def agregar(self, punto: PuntoDeVenta) -> None:
        self.guardados[punto.id] = punto

    async def guardar(self, punto: PuntoDeVenta) -> None:
        self.guardados[punto.id] = punto

    async def buscar_por_id(self, punto_id: UUID) -> PuntoDeVenta | None:
        return self.guardados.get(punto_id)

    async def listar(self) -> list[PuntoDeVenta]:
        return sorted(self.guardados.values(), key=lambda p: p.numero)

    async def tomar_para_emitir(self, punto_id: UUID) -> PuntoDeVenta | None:
        # Sin candado: acá no hay motor. Lo que este doble **no** puede simular es
        # justamente lo que hace correcto al método real.
        return self.guardados.get(punto_id)


class HabilitacionFalsa:
    def __init__(self, *, numeros: tuple[int, ...] = (1,), error: bool = False) -> None:
        self.numeros = numeros
        self.error = error

    async def puntos_habilitados(self, *, empresa_id: EmpresaId) -> tuple[PuntoHabilitado, ...]:
        del empresa_id
        if self.error:
            raise ArcaNoDisponible("ARCA no respondio")
        return tuple(PuntoHabilitado(numero=n) for n in self.numeros)


class PublicadorFalso:
    def __init__(self) -> None:
        self.eventos: list[EventoDeDominio] = []

    async def publicar(self, evento: EventoDeDominio) -> None:
        self.eventos.append(evento)


@pytest.fixture
def puntos() -> PuntosFalsos:
    return PuntosFalsos()


@pytest.fixture
def publicador() -> PublicadorFalso:
    return PublicadorFalso()


async def _registrar(
    puntos: PuntosFalsos,
    publicador: PublicadorFalso,
    *,
    numero: int = 1,
    habilitados: tuple[int, ...] = (1,),
    rol: RolUsuario = RolUsuario.ADMINISTRADOR,
) -> PuntoDeVenta:
    return await RegistrarPuntoDeVenta(
        puntos=puntos,
        habilitacion=HabilitacionFalsa(numeros=habilitados),
        publicador=publicador,
    ).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=rol,
        datos=DatosDePuntoDeVenta(numero=numero, descripcion="Casa central"),
        ahora=AHORA,
    )


async def test_un_punto_habilitado_en_arca_queda_disponible(
    puntos: PuntosFalsos, publicador: PublicadorFalso
) -> None:
    punto = await _registrar(puntos, publicador, numero=1, habilitados=(1, 2))

    assert punto.activo
    assert punto.puede_emitir
    assert len(publicador.eventos) == 1


async def test_un_punto_no_habilitado_se_rechaza_con_el_texto_de_la_historia(
    puntos: PuntosFalsos, publicador: PublicadorFalso
) -> None:
    """RN-03, y el mensaje es el de HU-E5-05, palabra por palabra."""
    with pytest.raises(PuntoDeVentaNoHabilitado) as exc:
        await _registrar(puntos, publicador, numero=7, habilitados=(1, 2))

    assert str(exc.value) == MENSAJE_NO_HABILITADO
    assert puntos.guardados == {}


async def test_un_punto_bloqueado_en_arca_tampoco_se_activa(
    puntos: PuntosFalsos, publicador: PublicadorFalso
) -> None:
    """ARCA reporta el punto pero bloqueado: reportado no es lo mismo que usable."""

    class SoloBloqueados:
        async def puntos_habilitados(self, *, empresa_id: EmpresaId) -> tuple[PuntoHabilitado, ...]:
            del empresa_id
            return (PuntoHabilitado(numero=3, bloqueado=True),)

    with pytest.raises(PuntoDeVentaNoHabilitado):
        await RegistrarPuntoDeVenta(
            puntos=puntos, habilitacion=SoloBloqueados(), publicador=publicador
        ).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.ADMINISTRADOR,
            datos=DatosDePuntoDeVenta(numero=3),
            ahora=AHORA,
        )


async def test_arca_caida_no_es_lo_mismo_que_arca_diciendo_que_no(
    puntos: PuntosFalsos, publicador: PublicadorFalso
) -> None:
    """Las dos fallas se mantienen separadas a propósito.

    «Ese punto no es tuyo» es un no permanente; «no pudimos preguntar» se reintenta en un
    minuto. Colapsarlas bloquearía un punto legítimo durante una caída, o activaría uno que
    ARCA nunca habilitó — y lo segundo aparece cuando rechazan la primera factura.
    """
    with pytest.raises(ArcaNoDisponible):
        await RegistrarPuntoDeVenta(
            puntos=puntos,
            habilitacion=HabilitacionFalsa(error=True),
            publicador=publicador,
        ).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.ADMINISTRADOR,
            datos=DatosDePuntoDeVenta(numero=1),
            ahora=AHORA,
        )


@pytest.mark.parametrize("rol", [RolUsuario.OPERADOR, RolUsuario.SOLO_LECTURA])
async def test_solo_un_administrador_administra_los_puntos(
    puntos: PuntosFalsos, publicador: PublicadorFalso, rol: RolUsuario
) -> None:
    """Más estricto que el mapeo del épico 4: esto es la numeración fiscal, no trabajo
    del día a día."""
    with pytest.raises(OperacionNoPermitida):
        await _registrar(puntos, publicador, rol=rol)

    assert puntos.guardados == {}


async def test_cualquier_rol_puede_listar(puntos: PuntosFalsos) -> None:
    assert await ListarPuntosDeVenta(puntos).ejecutar() == []


async def test_desactivar_conserva_los_numeradores(
    puntos: PuntosFalsos, publicador: PublicadorFalso
) -> None:
    """RN-04. Reactivar no puede reiniciar la numeración: ARCA se acuerda igual."""
    punto = await _registrar(puntos, publicador)
    punto.siguiente_numero(TipoComprobante.FACTURA_B)
    punto.siguiente_numero(TipoComprobante.FACTURA_B)

    await CambiarEstadoDePuntoDeVenta(
        puntos=puntos, habilitacion=HabilitacionFalsa(), publicador=publicador
    ).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.ADMINISTRADOR,
        punto_id=punto.id,
        activo=False,
        ahora=AHORA,
    )

    guardado = puntos.guardados[punto.id]
    assert not guardado.activo
    assert guardado.ultimo_numero(TipoComprobante.FACTURA_B) == 2


async def test_un_punto_desactivado_no_emite(
    puntos: PuntosFalsos, publicador: PublicadorFalso
) -> None:
    punto = await _registrar(puntos, publicador)
    punto.desactivar()

    with pytest.raises(InvarianteViolada):
        punto.siguiente_numero(TipoComprobante.FACTURA_B)


async def test_reactivar_vuelve_a_preguntarle_a_arca(
    puntos: PuntosFalsos, publicador: PublicadorFalso
) -> None:
    """Un punto puede quedar bloqueado en ARCA después de que nosotros lo registramos.

    Reactivarlo desde nuestra propia fila sería confiar en una foto para un permiso que
    vive en la AFIP.
    """
    punto = await _registrar(puntos, publicador)
    punto.desactivar()
    await puntos.guardar(punto)

    with pytest.raises(PuntoDeVentaNoHabilitado):
        await CambiarEstadoDePuntoDeVenta(
            puntos=puntos,
            habilitacion=HabilitacionFalsa(numeros=(2, 3)),  # el 1 ya no está
            publicador=publicador,
        ).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.ADMINISTRADOR,
            punto_id=punto.id,
            activo=True,
            ahora=AHORA,
        )


async def test_cambiar_el_estado_de_uno_que_no_existe_falla(
    puntos: PuntosFalsos, publicador: PublicadorFalso
) -> None:
    with pytest.raises(PuntoDeVentaInexistente):
        await CambiarEstadoDePuntoDeVenta(
            puntos=puntos, habilitacion=HabilitacionFalsa(), publicador=publicador
        ).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.ADMINISTRADOR,
            punto_id=uuid4(),
            activo=False,
            ahora=AHORA,
        )
