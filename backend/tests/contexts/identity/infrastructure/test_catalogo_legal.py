"""The file-backed legal catalogue (HU-E1-08 RN-01, RN-07; HU-E1-03 RN-04)."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path

import pytest
from cheatsheet.contexts.identity.domain.legal import DocumentoLegal, VersionDeDocumento
from cheatsheet.contexts.identity.infrastructure.legal.catalogo import (
    PUBLICADAS,
    RAIZ_DE_TEXTOS,
    CatalogoLegalEnArchivos,
    TextoLegalAlterado,
    VersionPublicada,
)


def _titulos(texto: str) -> list[str]:
    return [
        linea.removeprefix("## ").lower() for linea in texto.splitlines() if linea.startswith("## ")
    ]


# ------------------------------------------------------------------------------- case 3


@pytest.mark.parametrize(
    "publicada", PUBLICADAS, ids=lambda p: f"{p.version.documento}-{p.version.version}"
)
def test_el_hash_de_cada_archivo_publicado_coincide_con_el_declarado(publicada: VersionPublicada):
    archivo = (
        RAIZ_DE_TEXTOS
        / publicada.version.documento.value.lower()
        / f"{publicada.version.version}.md"
    )

    texto = archivo.read_text(encoding="utf-8")

    assert hashlib.sha256(texto.encode("utf-8")).hexdigest() == publicada.sha256, (
        "A published text is immutable: publish a new version instead of editing this one"
    )


def test_cada_archivo_de_textos_esta_declarado_en_el_catalogo():
    declarados = {
        RAIZ_DE_TEXTOS / p.version.documento.value.lower() / f"{p.version.version}.md"
        for p in PUBLICADAS
    }
    en_disco = set(RAIZ_DE_TEXTOS.glob("*/*.md"))

    assert en_disco == declarados


def test_cargar_un_texto_alterado_falla_al_arrancar(tmp_path: Path):
    (tmp_path / "privacidad").mkdir()
    (tmp_path / "privacidad" / "1.0.md").write_text("## Otro texto\n", encoding="utf-8")
    publicada = VersionPublicada(
        VersionDeDocumento(DocumentoLegal.PRIVACIDAD, "1.0", date(2026, 1, 1)), sha256="0" * 64
    )

    with pytest.raises(TextoLegalAlterado):
        CatalogoLegalEnArchivos(publicadas=(publicada,), raiz=tmp_path)


def test_el_hash_no_depende_de_los_saltos_de_linea_del_sistema(tmp_path: Path):
    (tmp_path / "privacidad").mkdir()
    contenido = "## Titulo\r\n\r\nParrafo\r\n"
    (tmp_path / "privacidad" / "1.0.md").write_bytes(contenido.encode("utf-8"))
    normalizado = contenido.replace("\r\n", "\n")
    publicada = VersionPublicada(
        VersionDeDocumento(DocumentoLegal.PRIVACIDAD, "1.0", date(2026, 1, 1)),
        sha256=hashlib.sha256(normalizado.encode("utf-8")).hexdigest(),
    )

    catalogo = CatalogoLegalEnArchivos(publicadas=(publicada,), raiz=tmp_path)

    assert catalogo.texto(DocumentoLegal.PRIVACIDAD, "1.0") == normalizado


# ------------------------------------------------------------------------------- case 4


def test_la_politica_vigente_cubre_los_apartados_minimos_de_la_ley_25326():
    catalogo = CatalogoLegalEnArchivos()
    version = max(
        (v for v in catalogo.versiones() if v.documento is DocumentoLegal.PRIVACIDAD),
        key=lambda v: v.vigente_desde,
    )
    texto = catalogo.texto(DocumentoLegal.PRIVACIDAD, version.version)
    titulos = " | ".join(_titulos(texto))

    for apartado in (
        "finalidad",
        "destinatarios",
        "responsable",
        "carácter",
        "acceso, rectificación y supresión",
        "clientes finales",
        "proveedores",
        "pagador",
    ):
        assert apartado in titulos, f"missing section: {apartado}"
    # The payer check against MercadoPago (D94) is explained under its own heading.
    assert "mercadopago" in texto.lower()


def test_los_datos_del_responsable_estan_marcados_para_completar():
    catalogo = CatalogoLegalEnArchivos()

    texto = catalogo.texto(DocumentoLegal.PRIVACIDAD, "1.0")

    assert "[a completar" in texto


def test_el_catalogo_publica_borradores_hasta_la_validacion_legal():
    catalogo = CatalogoLegalEnArchivos()

    assert catalogo.versiones()
    assert all(v.borrador for v in catalogo.versiones())


def test_los_terminos_arrancan_en_1_1_y_no_reusan_la_1_0_sin_texto():
    catalogo = CatalogoLegalEnArchivos()

    versiones = [v.version for v in catalogo.versiones() if v.documento is DocumentoLegal.TERMINOS]

    assert versiones == ["1.1"]


def test_los_textos_usan_solo_el_subconjunto_de_markdown_soportado():
    permitida = re.compile(r"^(## .+|- .+|[^#\-<>*`\[].*|\[a completar.*|\s*)$")
    for publicada in PUBLICADAS:
        catalogo = CatalogoLegalEnArchivos()
        texto = catalogo.texto(publicada.version.documento, publicada.version.version)
        for linea in texto.splitlines():
            assert permitida.match(linea), f"unsupported markdown: {linea!r}"
            assert "<" not in linea, "raw HTML is not part of the subset"


def test_texto_de_una_version_inexistente_es_un_error():
    catalogo = CatalogoLegalEnArchivos()

    with pytest.raises(KeyError):
        catalogo.texto(DocumentoLegal.TERMINOS, "9.9")
