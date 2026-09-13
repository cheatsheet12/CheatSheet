"""El invariante central de `VinculoDePlanilla`: solo Google Sheets escribe.

Todo lo demás de este agregado es estado. Esto es la regla que HU-E3-07 RN-01 lee antes
de escribir en la planilla de alguien, y por eso vive en el dominio y no en el formulario.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cheatsheet.contexts.spreadsheet_sync.domain.valores import (
    LIMITE_TAMANO_BYTES,
    MENSAJE_ARCHIVO_DEMASIADO_GRANDE,
    MENSAJE_FORMATO_NO_ACEPTADO,
    DireccionSync,
    ProveedorPlanilla,
    ReferenciaDeArchivo,
    validar_extension,
)
from cheatsheet.contexts.spreadsheet_sync.domain.vinculo import VinculoDePlanilla
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())


def _archivo() -> ReferenciaDeArchivo:
    return ReferenciaDeArchivo(
        clave="planillas/x/y.xlsx", nombre_original="clientes.xlsx", tamano_bytes=1024
    )


def _vinculo(**overrides: object) -> VinculoDePlanilla:
    base: dict[str, object] = {
        "id": uuid4(),
        "empresa_id": EMPRESA,
        "proveedor": ProveedorPlanilla.GOOGLE_SHEETS,
        "direccion": DireccionSync.SOLO_LECTURA,
        "hoja_empresa": "Clientes",
        "identificador_externo": "1AbCdEf",
        "created_at": AHORA,
        "updated_at": AHORA,
    }
    base.update(overrides)
    return VinculoDePlanilla(**base)  # type: ignore[arg-type]


def test_google_sheets_admite_lectura_y_escritura() -> None:
    """Caso 1 del plan."""
    vinculo = _vinculo(direccion=DireccionSync.LECTURA_Y_ESCRITURA)

    assert vinculo.escribe_de_vuelta
    assert vinculo.admite_sincronizacion_incremental


@pytest.mark.parametrize(
    ("proveedor", "extra"),
    [
        (ProveedorPlanilla.EXCEL_ONLINE, {"identificador_externo": "item-1"}),
        (ProveedorPlanilla.ARCHIVO, {"archivo": _archivo(), "identificador_externo": None}),
    ],
)
def test_solo_google_puede_vincularse_para_escribir(
    proveedor: ProveedorPlanilla, extra: dict[str, object]
) -> None:
    """Caso 2 del plan, y el invariante que justifica el agregado.

    Excel Online es de solo lectura por el proveedor (precondición de HU-E3-07) y un
    archivo subido es una foto: escribirle produciría un archivo que nadie vuelve a abrir.
    """
    with pytest.raises(InvarianteViolada):
        _vinculo(proveedor=proveedor, direccion=DireccionSync.LECTURA_Y_ESCRITURA, **extra)


def test_un_archivo_no_admite_sincronizacion_incremental() -> None:
    """HU-E3-04 sobre una foto compararía el archivo consigo mismo para siempre."""
    vinculo = _vinculo(
        proveedor=ProveedorPlanilla.ARCHIVO, archivo=_archivo(), identificador_externo=None
    )

    assert not vinculo.admite_sincronizacion_incremental
    assert not vinculo.escribe_de_vuelta


def test_un_vinculo_pausado_no_se_sincroniza() -> None:
    """RN-04: la estructura cambió, así que la sincronización automática se detiene."""
    vinculo = _vinculo()
    vinculo.pausar(motivo="La estructura de la planilla cambio", ahora=AHORA)

    assert vinculo.pausado
    assert not vinculo.admite_sincronizacion_incremental
    assert vinculo.motivo_de_pausa == "La estructura de la planilla cambio"


def test_pausar_dos_veces_no_es_un_error() -> None:
    """El barrido puede encontrar el mismo encabezado cambiado en dos corridas seguidas."""
    vinculo = _vinculo()
    vinculo.pausar(motivo="primera", ahora=AHORA)
    vinculo.pausar(motivo="segunda", ahora=AHORA)

    assert vinculo.motivo_de_pausa == "segunda"


def test_no_se_reanuda_sin_un_mapeo_confirmado() -> None:
    """Reanudar sin mapeo dejaría al barrido leyendo columnas que ya no significan lo mismo."""
    vinculo = _vinculo()
    vinculo.pausar(motivo="cambio", ahora=AHORA)

    with pytest.raises(InvarianteViolada):
        vinculo.reanudar(ahora=AHORA)

    vinculo.asignar_mapeo(uuid4(), ahora=AHORA)
    vinculo.reanudar(ahora=AHORA)
    assert not vinculo.pausado


def test_un_vinculo_de_solo_lectura_rechaza_registrar_una_escritura() -> None:
    """Una marca de escritura sobre un vínculo de solo lectura sería evidencia falsa."""
    vinculo = _vinculo(direccion=DireccionSync.SOLO_LECTURA)

    with pytest.raises(InvarianteViolada):
        vinculo.registrar_escritura(ahora=AHORA)


def test_un_vinculo_de_google_sin_identificador_es_rechazado() -> None:
    with pytest.raises(InvarianteViolada):
        _vinculo(identificador_externo=None)


def test_un_vinculo_de_archivo_sin_archivo_es_rechazado() -> None:
    with pytest.raises(InvarianteViolada):
        _vinculo(proveedor=ProveedorPlanilla.ARCHIVO, identificador_externo=None)


@pytest.mark.parametrize("nombre", ["clientes.xlsx", "Clientes.XLS", "datos.csv"])
def test_las_tres_extensiones_de_la_historia_se_aceptan(nombre: str) -> None:
    assert validar_extension(nombre) == nombre.strip()


@pytest.mark.parametrize("nombre", ["clientes.pdf", "clientes", "clientes.xlsx.exe", "  "])
def test_cualquier_otra_extension_se_rechaza_con_el_texto_de_la_historia(nombre: str) -> None:
    """Caso 4 del plan. El mensaje es el de HU-E3-03, palabra por palabra."""
    with pytest.raises(EntradaInvalida) as exc:
        validar_extension(nombre)

    assert str(exc.value) == MENSAJE_FORMATO_NO_ACEPTADO


def test_un_archivo_de_mas_de_25_mb_se_rechaza_con_el_texto_de_la_historia() -> None:
    """Caso 5 del plan."""
    with pytest.raises(EntradaInvalida) as exc:
        ReferenciaDeArchivo(
            clave="k", nombre_original="grande.xlsx", tamano_bytes=LIMITE_TAMANO_BYTES + 1
        )

    assert str(exc.value) == MENSAJE_ARCHIVO_DEMASIADO_GRANDE


def test_un_archivo_vacio_se_rechaza() -> None:
    with pytest.raises(EntradaInvalida):
        ReferenciaDeArchivo(clave="k", nombre_original="vacio.xlsx", tamano_bytes=0)
