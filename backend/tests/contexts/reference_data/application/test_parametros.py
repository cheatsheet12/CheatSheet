"""HS-T4: sincronizar el catálogo de ARCA sin perder lo que decía antes.

Dos propiedades sostienen esta unidad y las dos se prueban acá:

1. **Un valor nuevo cierra al anterior, no lo pisa** (RN-02). El histórico es la razón de
   ser de la tabla: un comprobante emitido en marzo se explica con el parámetro de marzo, y
   si lo pisáramos no habría forma de reconstruir por qué decía lo que decía.
2. **Fallar conserva lo anterior** (RN-04). Vaciar y reintentar dejaría a la facturación sin
   contra qué validar durante la ventana de la falla, que es exactamente cuando alguien va
   a querer emitir.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from cheatsheet.contexts.reference_data.application.errors import CatalogoNoDisponible
from cheatsheet.contexts.reference_data.application.parametros import (
    ParametroVigenteA,
    SincronizarParametrosFiscales,
)
from cheatsheet.contexts.reference_data.application.ports import EntradaDeCatalogo
from cheatsheet.contexts.reference_data.domain.parametro import (
    ParametroFiscal,
    TipoCatalogoFiscal,
)
from cheatsheet.contexts.reference_data.infrastructure.wsfe_catalogos import CatalogosSimulados
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import InvarianteViolada
from cheatsheet.shared.events import EventoDeDominio

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())
MARZO = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
JUNIO = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
IVA = TipoCatalogoFiscal.ALICUOTA_IVA


class ParametrosFalsos:
    def __init__(self) -> None:
        self.guardados: list[ParametroFiscal] = []

    async def agregar(self, parametro: ParametroFiscal) -> None:
        self.guardados.append(parametro)

    async def cerrar(self, parametro: ParametroFiscal) -> None:
        self.guardados = [parametro if p.id == parametro.id else p for p in self.guardados]

    async def vigentes(self, *, tipo: TipoCatalogoFiscal | None = None) -> list[ParametroFiscal]:
        return [
            p for p in self.guardados if p.fecha_hasta is None and (tipo is None or p.tipo is tipo)
        ]

    async def buscar_vigente_a(
        self, *, tipo: TipoCatalogoFiscal, codigo: str, fecha: date
    ) -> ParametroFiscal | None:
        return next(
            (
                p
                for p in self.guardados
                if p.tipo is tipo and p.codigo == codigo and p.vigente_a(fecha)
            ),
            None,
        )


class CatalogosFalsos:
    def __init__(
        self, entradas: tuple[EntradaDeCatalogo, ...] = (), error: str | None = None
    ) -> None:
        self.entradas = entradas
        self.error = error
        self.llamadas = 0

    async def obtener(self, *, empresa_id: EmpresaId) -> tuple[EntradaDeCatalogo, ...]:
        del empresa_id
        self.llamadas += 1
        if self.error is not None:
            raise CatalogoNoDisponible(self.error)
        return self.entradas


class PublicadorFalso:
    def __init__(self) -> None:
        self.eventos: list[EventoDeDominio] = []

    async def publicar(self, evento: EventoDeDominio) -> None:
        self.eventos.append(evento)


def _entrada(codigo: str, valor: str) -> EntradaDeCatalogo:
    return EntradaDeCatalogo(tipo=IVA, codigo=codigo, valor=valor)


async def _sincronizar(
    parametros: ParametrosFalsos,
    catalogos: CatalogosFalsos,
    publicador: PublicadorFalso,
    ahora: datetime,
) -> object:
    # Sin `type: ignore`: los dobles satisfacen los protocolos de verdad, y mypy lo
    # verifica. Un doble que dejara de cumplir el puerto fallaría acá, que es exactamente
    # lo que `tests/conftest.py` explica sobre no usar `Mock`.
    return await SincronizarParametrosFiscales(
        parametros=parametros,
        catalogos=catalogos,
        publicador=publicador,
    ).ejecutar(empresa_id=EMPRESA, ahora=ahora)


@pytest.fixture
def parametros() -> ParametrosFalsos:
    return ParametrosFalsos()


@pytest.fixture
def publicador() -> PublicadorFalso:
    return PublicadorFalso()


async def test_un_parametro_nuevo_se_guarda_con_su_vigencia(
    parametros: ParametrosFalsos, publicador: PublicadorFalso
) -> None:
    """RN-01."""
    resultado = await _sincronizar(
        parametros, CatalogosFalsos((_entrada("5", "0.21"),)), publicador, MARZO
    )

    assert resultado.nuevos == 1  # type: ignore[attr-defined]
    assert parametros.guardados[0].fecha_desde == MARZO.date()
    assert parametros.guardados[0].fecha_hasta is None


async def test_un_valor_que_cambio_cierra_al_anterior_y_no_lo_pisa(
    parametros: ParametrosFalsos, publicador: PublicadorFalso
) -> None:
    """RN-02, y la razón de ser de la tabla.

    Después de la segunda corrida tienen que existir **las dos** filas: la de marzo cerrada
    y la de junio abierta. Un comprobante emitido en abril se explica con la primera.
    """
    await _sincronizar(parametros, CatalogosFalsos((_entrada("5", "0.21"),)), publicador, MARZO)
    await _sincronizar(parametros, CatalogosFalsos((_entrada("5", "0.25"),)), publicador, JUNIO)

    assert len(parametros.guardados) == 2
    vieja = next(p for p in parametros.guardados if p.valor == "0.21")
    nueva = next(p for p in parametros.guardados if p.valor == "0.25")
    assert vieja.fecha_hasta == date(2026, 6, 9)  # el día anterior: no se solapan
    assert nueva.fecha_desde == JUNIO.date()
    assert not vieja.se_solapa_con(nueva)


async def test_la_consulta_devuelve_el_vigente_a_una_fecha_y_no_el_de_hoy(
    parametros: ParametrosFalsos, publicador: PublicadorFalso
) -> None:
    """RN-03. El test que evita reimprimir una factura de marzo con la alícuota de junio."""
    await _sincronizar(parametros, CatalogosFalsos((_entrada("5", "0.21"),)), publicador, MARZO)
    await _sincronizar(parametros, CatalogosFalsos((_entrada("5", "0.25"),)), publicador, JUNIO)

    consulta = ParametroVigenteA(parametros)

    en_abril = await consulta.ejecutar(tipo=IVA, codigo="5", fecha=date(2026, 4, 15))
    en_julio = await consulta.ejecutar(tipo=IVA, codigo="5", fecha=date(2026, 7, 15))

    assert en_abril.como_decimal() == Decimal("0.21")
    assert en_julio.como_decimal() == Decimal("0.25")


async def test_una_sincronizacion_fallida_conserva_el_ultimo_vigente(
    parametros: ParametrosFalsos, publicador: PublicadorFalso
) -> None:
    """RN-04. Vaciar y reintentar dejaría a la facturación sin catálogo justo cuando falla."""
    await _sincronizar(parametros, CatalogosFalsos((_entrada("5", "0.21"),)), publicador, MARZO)

    resultado = await _sincronizar(
        parametros, CatalogosFalsos(error="ARCA no respondio"), publicador, JUNIO
    )

    assert resultado.fallo  # type: ignore[attr-defined]
    assert len(parametros.guardados) == 1
    assert parametros.guardados[0].fecha_hasta is None
    assert parametros.guardados[0].valor == "0.21"


async def test_una_respuesta_vacia_tampoco_borra_nada(
    parametros: ParametrosFalsos, publicador: PublicadorFalso
) -> None:
    """ARCA devolviendo nada es indistinguible de ARCA teniendo un mal día."""
    await _sincronizar(parametros, CatalogosFalsos((_entrada("5", "0.21"),)), publicador, MARZO)

    resultado = await _sincronizar(parametros, CatalogosFalsos(()), publicador, JUNIO)

    assert resultado.fallo  # type: ignore[attr-defined]
    assert len(parametros.guardados) == 1


async def test_un_valor_identico_al_vigente_no_crea_una_fila_nueva(
    parametros: ParametrosFalsos, publicador: PublicadorFalso
) -> None:
    """Si no, el histórico sería un log de sincronizaciones y no del catálogo."""
    await _sincronizar(parametros, CatalogosFalsos((_entrada("5", "0.21"),)), publicador, MARZO)

    resultado = await _sincronizar(
        parametros, CatalogosFalsos((_entrada("5", "0.21"),)), publicador, JUNIO
    )

    assert resultado.nuevos == 0  # type: ignore[attr-defined]
    assert resultado.cerrados == 0  # type: ignore[attr-defined]
    assert len(parametros.guardados) == 1


async def test_la_sincronizacion_queda_auditada(
    parametros: ParametrosFalsos, publicador: PublicadorFalso
) -> None:
    await _sincronizar(parametros, CatalogosFalsos((_entrada("5", "0.21"),)), publicador, MARZO)

    assert len(publicador.eventos) == 1
    # El planificador la corrió, no una persona.
    assert publicador.eventos[0].usuario_id is None  # type: ignore[attr-defined]


async def test_pedir_un_parametro_que_no_existe_falla_en_vez_de_devolver_none(
    parametros: ParametrosFalsos,
) -> None:
    """Un `None` que llega hasta un comprobante es un campo vacío en un documento fiscal."""
    with pytest.raises(InvarianteViolada):
        await ParametroVigenteA(parametros).ejecutar(tipo=IVA, codigo="99", fecha=date(2026, 4, 1))


async def test_el_simulado_trae_los_codigos_reales_de_arca() -> None:
    """Un simulador con códigos inventados dejaría pasar tests que ARCA rechazaría.

    `1` es Factura A y `5` es la alícuota del 21 %: son los códigos publicados, no
    invenciones cómodas.
    """
    entradas = await CatalogosSimulados().obtener(empresa_id=EMPRESA)

    por_clave = {(e.tipo, e.codigo): e.valor for e in entradas}
    assert por_clave[(TipoCatalogoFiscal.TIPO_COMPROBANTE, "1")] == "Factura A"
    assert por_clave[(IVA, "5")] == "0.21"
    # Y la alícuota se puede convertir a `Decimal` sin pasar por un float.
    assert Decimal(por_clave[(IVA, "4")]) == Decimal("0.105")
