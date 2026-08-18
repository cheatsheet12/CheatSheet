"""The aggregate's own rules — cases 1, 2 and 3 of the plan."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from cheatsheet.contexts.integrations.domain.configuracion import ConfiguracionDeIntegracion
from cheatsheet.contexts.integrations.domain.valores import (
    Ambiente,
    CredencialCifrada,
    EstadoDeConexion,
    SistemaExterno,
)
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

from tests.conftest import INSTANTE_FIJO

CREDENCIAL = CredencialCifrada(contenido=b"cifrado:x", algoritmo="FALSO/v1")
OTRA = CredencialCifrada(contenido=b"cifrado:y", algoritmo="FALSO/v1")


def _conectada() -> ConfiguracionDeIntegracion:
    return ConfiguracionDeIntegracion.conectar(
        id=uuid4(),
        empresa_id=EmpresaId(uuid4()),
        sistema=SistemaExterno.ARCA,
        credencial=CREDENCIAL,
        ambiente=Ambiente.HOMOLOGACION,
        ahora=INSTANTE_FIJO,
    )


def test_conectar_deja_conectado_y_sella_la_credencial() -> None:
    configuracion = _conectada()

    assert configuracion.estado is EstadoDeConexion.CONECTADO
    assert configuracion.esta_conectada
    assert configuracion.credencial is CREDENCIAL
    assert configuracion.verificado_en == INSTANTE_FIJO


def test_una_verificacion_que_confirma_el_estado_no_emite_evento() -> None:
    """The rule that keeps the Log de Operaciones from becoming a heartbeat."""
    configuracion = _conectada()
    despues = INSTANTE_FIJO + timedelta(minutes=5)

    cambio = configuracion.registrar_verificacion(EstadoDeConexion.CONECTADO, None, despues)

    assert cambio is None
    # The timestamp still moves: RN-03 shows when the last check ran, and a check that
    # confirmed the status is still a check.
    assert configuracion.verificado_en == despues


def test_una_verificacion_que_cambia_el_estado_si_emite_evento() -> None:
    configuracion = _conectada()
    despues = INSTANTE_FIJO + timedelta(minutes=5)

    cambio = configuracion.registrar_verificacion(
        EstadoDeConexion.ATENCION, "Latencia alta", despues
    )

    assert cambio is not None
    assert cambio.anterior is EstadoDeConexion.CONECTADO
    assert cambio.nuevo is EstadoDeConexion.ATENCION
    assert cambio.detalle == "Latencia alta"
    assert "ARCA" in cambio.descripcion


def test_desactivar_lleva_a_no_conectado_con_el_motivo() -> None:
    """HU-E2-01 RN-04 and HU-E2-02 RN-03. Nothing triggers this yet; the transition exists."""
    configuracion = _conectada()

    cambio = configuracion.desactivar("Certificado vencido", INSTANTE_FIJO)

    assert configuracion.estado is EstadoDeConexion.NO_CONECTADO
    assert configuracion.detalle_estado == "Certificado vencido"
    assert not configuracion.esta_conectada
    assert cambio is not None


def test_reconectar_reemplaza_la_credencial() -> None:
    configuracion = _conectada()
    configuracion.registrar_verificacion(EstadoDeConexion.NO_CONECTADO, "caido", INSTANTE_FIJO)

    cambio = configuracion.reconectar(
        credencial=OTRA, ambiente=Ambiente.HOMOLOGACION, ahora=INSTANTE_FIJO
    )

    assert configuracion.credencial is OTRA
    assert configuracion.estado is EstadoDeConexion.CONECTADO
    assert cambio is not None


def test_reconectar_en_otro_ambiente_es_rechazado() -> None:
    """A row created against homologación must not silently become a production one."""
    configuracion = _conectada()

    with pytest.raises(InvarianteViolada, match="PRODUCCION"):
        configuracion.reconectar(credencial=OTRA, ambiente=Ambiente.PRODUCCION, ahora=INSTANTE_FIJO)


def test_una_credencial_cifrada_vacia_es_rechazada() -> None:
    with pytest.raises(EntradaInvalida):
        CredencialCifrada(contenido=b"", algoritmo="FALSO/v1")


def test_una_credencial_sin_algoritmo_es_rechazada() -> None:
    """Ciphertext with no algorithm is ciphertext nobody can read back."""
    with pytest.raises(EntradaInvalida):
        CredencialCifrada(contenido=b"x", algoritmo="   ")


def test_un_detalle_en_blanco_se_normaliza_a_none() -> None:
    configuracion = _conectada()

    configuracion.registrar_verificacion(EstadoDeConexion.ATENCION, "   ", INSTANTE_FIJO)

    assert configuracion.detalle_estado is None


def test_un_detalle_muy_largo_se_recorta() -> None:
    """The column is 300 characters; a provider that returns an essay must not break the write."""
    configuracion = _conectada()

    configuracion.registrar_verificacion(EstadoDeConexion.ATENCION, "x" * 400, INSTANTE_FIJO)

    assert configuracion.detalle_estado == "x" * 300
