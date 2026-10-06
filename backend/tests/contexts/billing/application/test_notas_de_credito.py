"""HU-E5-04 — anular un comprobante con una nota de crédito.

Lo que se prueba acá es lo que sólo existe **porque hay un original**: el vínculo (RN-01),
el tipo que lo determina el original (RN-02), el tope contra lo que queda (RN-03) y el
estado de anulación (RN-05, decisión D19).

Todo lo demás —el número bajo candado, la emisión asíncrona, la reconciliación— es de la
unidad anterior y está probado ahí. Que sea así es el punto: un segundo camino de emisión
sería un segundo lugar donde D14, D17 y D18 pueden estar mal, y una nota de crédito también
lleva CAE.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from cheatsheet.contexts.billing.application.emision import EmitirComprobante
from cheatsheet.contexts.billing.application.errors import (
    ComprobanteInexistente,
    ComprobanteNoAnulable,
    MontoDeNotaExcedido,
)
from cheatsheet.contexts.billing.application.notas_de_credito import (
    MENSAJE_MONTO_EXCEDIDO,
    MENSAJE_SIN_ORIGEN,
    EmitirNotaDeCredito,
    EstadoDeAnulacion,
    reflejar_anulacion,
)
from cheatsheet.contexts.billing.application.ports import FiltrosDeComprobante
from cheatsheet.contexts.billing.domain.comprobante import (
    CAE,
    AlicuotaIVA,
    Comprobante,
    EstadoComprobante,
    ItemDeComprobante,
    Receptor,
)
from cheatsheet.contexts.billing.domain.punto_de_venta import PuntoDeVenta, TipoComprobante
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.fiscal import CondicionIVA
from cheatsheet.shared.roles import RolUsuario

from tests.contexts.billing.application.test_emision import (
    ArcaFalso,
    ColaFalsa,
    ComprobantesFalsos,
    PublicadorFalso,
    PuntosFalsos,
)

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
USUARIO = UsuarioId(uuid4())
RI = CondicionIVA.RESPONSABLE_INSCRIPTO
UN_CAE = CAE(codigo="75123456789012", vence_el=date(2026, 9, 17))


def _item(precio: str = "1000.00", cantidad: str = "2") -> ItemDeComprobante:
    return ItemDeComprobante(
        id=uuid4(),
        descripcion="Corte de pelo",
        cantidad=Decimal(cantidad),
        precio_unitario=Decimal(precio),
        alicuota_iva=AlicuotaIVA.GENERAL,
    )


@pytest.fixture
def punto() -> PuntoDeVenta:
    return PuntoDeVenta(id=uuid4(), empresa_id=EMPRESA, numero=1, created_at=AHORA)


def _original(punto: PuntoDeVenta, *, autorizado: bool = True) -> Comprobante:
    """Total de $2420,00: dos ítems de $1000 más el 21 %."""
    comprobante = Comprobante(
        id=uuid4(),
        empresa_id=EMPRESA,
        cliente_id=uuid4(),
        punto_de_venta_id=punto.id,
        tipo=TipoComprobante.FACTURA_A,
        receptor=Receptor(nombre="Acme SA", cuit="30712345671", condicion_iva=RI),
        emisor_condicion_iva=RI,
        created_at=AHORA,
    )
    comprobante.agregar_item(_item())
    if autorizado:
        comprobante.validar()
        comprobante.enviar_a_arca(1, AHORA)
        comprobante.autorizar(UN_CAE)
    return comprobante


def _emisor(
    punto: PuntoDeVenta, comprobantes: ComprobantesFalsos, arca: ArcaFalso
) -> EmitirNotaDeCredito:
    return EmitirNotaDeCredito(
        comprobantes=comprobantes,
        emitir=EmitirComprobante(
            comprobantes=comprobantes,
            puntos=PuntosFalsos(punto),
            arca=arca,
            cola=ColaFalsa(),
            publicador=PublicadorFalso(),
        ),
    )


# ------------------------------------------------------------------ el vinculo y el tipo


async def test_la_nota_hereda_el_tipo_y_el_receptor_del_original(punto: PuntoDeVenta) -> None:
    """RN-02: lo determina el sistema, nunca lo elige el usuario.

    Y el receptor se copia del original, no se relee del catálogo: lo que se reversa es lo
    que se emitió, y el cliente puede haber editado su nombre desde entonces.
    """
    comprobantes = ComprobantesFalsos()
    original = _original(punto)
    await comprobantes.agregar(original)

    nota = await _emisor(punto, comprobantes, ArcaFalso()).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        origen_id=original.id,
        items=[_item()],
        ahora=AHORA,
    )

    assert nota.tipo is TipoComprobante.NOTA_CREDITO_A
    assert nota.comprobante_origen_id == original.id
    assert nota.receptor == original.receptor
    assert nota.punto_de_venta_id == original.punto_de_venta_id
    # Sale por el mismo camino que cualquier comprobante: en vuelo y encolada.
    assert nota.esta_en_vuelo


async def test_sin_comprobante_de_referencia_usa_el_texto_de_la_historia(
    punto: PuntoDeVenta,
) -> None:
    """RN-01. Bajo RLS «no es tuyo» y «no existe» son la misma respuesta, y la frase de la
    historia cubre las dos sin confirmar ninguna."""
    with pytest.raises(ComprobanteInexistente) as exc:
        await _emisor(punto, ComprobantesFalsos(), ArcaFalso()).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            origen_id=uuid4(),
            items=[_item()],
            ahora=AHORA,
        )

    assert str(exc.value) == MENSAJE_SIN_ORIGEN


@pytest.mark.parametrize("estado", [EstadoComprobante.BORRADOR, EstadoComprobante.ENVIADO_A_ARCA])
async def test_solo_se_anula_un_comprobante_autorizado(
    punto: PuntoDeVenta, estado: EstadoComprobante
) -> None:
    """RN-01. Anular algo que ARCA no autorizó sería reversar una venta que no documentó
    nadie — y si está en vuelo, todavía no sabemos si la documentó."""
    comprobantes = ComprobantesFalsos()
    original = _original(punto, autorizado=False)
    if estado is EstadoComprobante.ENVIADO_A_ARCA:
        original.validar()
        original.enviar_a_arca(1, AHORA)
    await comprobantes.agregar(original)

    with pytest.raises(ComprobanteNoAnulable):
        await _emisor(punto, comprobantes, ArcaFalso()).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            origen_id=original.id,
            items=[_item()],
            ahora=AHORA,
        )


async def test_una_nota_de_credito_no_se_anula_con_otra(punto: PuntoDeVenta) -> None:
    """El dominio lo impide: `TipoComprobante.nota_de_credito` rompe para una nota."""
    comprobantes = ComprobantesFalsos()
    original = _original(punto)
    await comprobantes.agregar(original)
    nota = await _emisor(punto, comprobantes, ArcaFalso()).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        origen_id=original.id,
        items=[_item()],
        ahora=AHORA,
    )
    nota.autorizar(UN_CAE)
    await comprobantes.guardar(nota)

    with pytest.raises(ComprobanteNoAnulable):
        await _emisor(punto, comprobantes, ArcaFalso()).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            origen_id=nota.id,
            items=[_item()],
            ahora=AHORA,
        )


# ------------------------------------------------------------------ el tope · RN-03


async def test_un_monto_mayor_al_original_se_rechaza_con_el_texto_de_la_historia(
    punto: PuntoDeVenta,
) -> None:
    comprobantes = ComprobantesFalsos()
    original = _original(punto)  # $2420,00
    await comprobantes.agregar(original)

    with pytest.raises(MontoDeNotaExcedido) as exc:
        await _emisor(punto, comprobantes, ArcaFalso()).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            origen_id=original.id,
            items=[_item(precio="9000.00", cantidad="1")],
            ahora=AHORA,
        )

    assert str(exc.value) == MENSAJE_MONTO_EXCEDIDO


async def test_dos_notas_parciales_son_legitimas_y_la_tercera_no(
    punto: PuntoDeVenta,
) -> None:
    """**El tope es contra lo que queda, no contra el total del original.**

    Dos notas de la mitad cada una son correctas; un chequeo contra el total permitiría una
    tercera, que reversaría más de lo que se facturó.
    """
    comprobantes = ComprobantesFalsos()
    original = _original(punto)  # $2420,00
    await comprobantes.agregar(original)
    emisor = _emisor(punto, comprobantes, ArcaFalso())

    for _ in range(2):
        nota = await emisor.ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            origen_id=original.id,
            items=[_item(precio="1000.00", cantidad="1")],  # $1210,00
            ahora=AHORA,
        )
        nota.autorizar(UN_CAE)
        await comprobantes.guardar(nota)

    with pytest.raises(MontoDeNotaExcedido):
        await emisor.ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            origen_id=original.id,
            items=[_item(precio="1000.00", cantidad="1")],
            ahora=AHORA,
        )


async def test_una_nota_rechazada_no_consume_el_cupo(punto: PuntoDeVenta) -> None:
    """**Decisión D19: sólo las autorizadas reversan.**

    Una que ARCA rechazó no reversó nada, así que el original sigue entero — y si esto
    contara mal, un error de ARCA dejaría a la empresa sin poder anular su propia factura.
    """
    comprobantes = ComprobantesFalsos()
    original = _original(punto)
    await comprobantes.agregar(original)
    emisor = _emisor(punto, comprobantes, ArcaFalso())

    fallida = await emisor.ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        origen_id=original.id,
        items=[_item()],  # el total entero
        ahora=AHORA,
    )
    fallida.rechazar("Error 10016: algo")
    await comprobantes.guardar(fallida)

    # El cupo sigue completo, así que esta pasa.
    buena = await emisor.ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        origen_id=original.id,
        items=[_item()],
        ahora=AHORA,
    )

    assert buena.total == original.total


async def test_una_nota_en_vuelo_tampoco_reversa_todavia(punto: PuntoDeVenta) -> None:
    """No es un descuido: mientras no sepamos si ARCA la autorizó, no reversó nada.

    Lo que sí protege contra reversar dos veces es que **el segundo intento también se
    reconcilia** (D17), no un contador optimista acá.
    """
    comprobantes = ComprobantesFalsos()
    original = _original(punto)
    await comprobantes.agregar(original)
    await _emisor(punto, comprobantes, ArcaFalso()).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        origen_id=original.id,
        items=[_item()],
        ahora=AHORA,
    )

    estado = await EstadoDeAnulacion(comprobantes).ejecutar(original.id)

    assert estado.total_anulado == Decimal("0.00")
    assert estado.disponible == original.total


# ------------------------------------------------------------------ RN-05 · D19


async def test_una_anulacion_total_deja_el_original_anulado(punto: PuntoDeVenta) -> None:
    comprobantes = ComprobantesFalsos()
    original = _original(punto)
    await comprobantes.agregar(original)
    nota = await _emisor(punto, comprobantes, ArcaFalso()).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        origen_id=original.id,
        items=[_item()],
        ahora=AHORA,
    )
    nota.autorizar(UN_CAE)
    await comprobantes.guardar(nota)

    await reflejar_anulacion(comprobantes, nota)

    assert original.estado is EstadoComprobante.ANULADO
    estado = await EstadoDeAnulacion(comprobantes).ejecutar(original.id)
    assert estado.es_total


async def test_una_anulacion_parcial_no_cambia_el_estado_del_original(
    punto: PuntoDeVenta,
) -> None:
    """**La anulación parcial no es un estado.** Es un monto.

    El original sigue `AUTORIZADO` porque eso es lo que es: un comprobante vigente por su
    saldo. Marcarlo `ANULADO` diría que ya no vale nada, y valdría la mitad.
    """
    comprobantes = ComprobantesFalsos()
    original = _original(punto)
    await comprobantes.agregar(original)
    nota = await _emisor(punto, comprobantes, ArcaFalso()).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        origen_id=original.id,
        items=[_item(precio="1000.00", cantidad="1")],  # la mitad
        ahora=AHORA,
    )
    nota.autorizar(UN_CAE)
    await comprobantes.guardar(nota)

    await reflejar_anulacion(comprobantes, nota)

    assert original.estado is EstadoComprobante.AUTORIZADO
    estado = await EstadoDeAnulacion(comprobantes).ejecutar(original.id)
    assert estado.es_parcial
    assert estado.total_anulado == Decimal("1210.00")
    assert estado.disponible == Decimal("1210.00")


async def test_reflejar_la_anulacion_dos_veces_no_rompe(punto: PuntoDeVenta) -> None:
    """Idempotente, y viene de que `ANULADO → ANULADO` no está en la tabla de transiciones.

    Importa porque esto lo llama el worker, y Celery reentrega.
    """
    comprobantes = ComprobantesFalsos()
    original = _original(punto)
    await comprobantes.agregar(original)
    nota = await _emisor(punto, comprobantes, ArcaFalso()).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        origen_id=original.id,
        items=[_item()],
        ahora=AHORA,
    )
    nota.autorizar(UN_CAE)
    await comprobantes.guardar(nota)

    await reflejar_anulacion(comprobantes, nota)
    await reflejar_anulacion(comprobantes, nota)

    assert original.estado is EstadoComprobante.ANULADO


async def test_un_comprobante_comun_no_dispara_ninguna_anulacion(
    punto: PuntoDeVenta,
) -> None:
    """Sin `comprobante_origen_id` no hay nada que reflejar, y no se consulta la base."""
    comprobantes = ComprobantesFalsos()
    original = _original(punto)
    await comprobantes.agregar(original)

    await reflejar_anulacion(comprobantes, original)

    assert original.estado is EstadoComprobante.AUTORIZADO


async def test_el_estado_de_anulacion_de_uno_inexistente_falla() -> None:
    with pytest.raises(ComprobanteInexistente):
        await EstadoDeAnulacion(ComprobantesFalsos()).ejecutar(uuid4())


async def test_la_nota_aparece_en_el_listado_como_cualquier_comprobante(
    punto: PuntoDeVenta,
) -> None:
    """El criterio de aceptación: «La nota de crédito aparece en el listado con estado
    Pendiente». No hay listado aparte, y no debe haberlo: es un comprobante."""
    comprobantes = ComprobantesFalsos()
    original = _original(punto)
    await comprobantes.agregar(original)
    nota = await _emisor(punto, comprobantes, ArcaFalso()).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        origen_id=original.id,
        items=[_item()],
        ahora=AHORA,
    )

    listado = await comprobantes.listar(FiltrosDeComprobante())

    assert nota.id in {uno.id for uno in listado}


async def test_notas_de_solo_devuelve_las_del_original_pedido(punto: PuntoDeVenta) -> None:
    comprobantes = ComprobantesFalsos()
    uno = _original(punto)
    otro = _original(punto)
    await comprobantes.agregar(uno)
    await comprobantes.agregar(otro)
    emisor = _emisor(punto, comprobantes, ArcaFalso())
    nota = await emisor.ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        origen_id=uno.id,
        items=[_item(precio="10.00", cantidad="1")],
        ahora=AHORA,
    )

    del_uno: list[Comprobante] = await comprobantes.notas_de(uno.id)
    del_otro: list[Comprobante] = await comprobantes.notas_de(otro.id)

    assert [n.id for n in del_uno] == [nota.id]
    assert del_otro == []
