"""The aggregate's own rules — cases 1, 2 and 3 of the plan."""

from __future__ import annotations

from datetime import datetime, timedelta
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


# ------------------------------------------- conexion-whatsapp: casos 1 a 6 y 20 del plan


def _pendiente(ahora: datetime = INSTANTE_FIJO) -> ConfiguracionDeIntegracion:
    return ConfiguracionDeIntegracion.registrar(
        id=uuid4(),
        empresa_id=EmpresaId(uuid4()),
        sistema=SistemaExterno.WHATSAPP,
        credencial=CREDENCIAL,
        ambiente=Ambiente.HOMOLOGACION,
        ahora=ahora,
        estado=EstadoDeConexion.PENDIENTE,
        detalle="Meta esta revisando el numero",
    )


def test_pendiente_es_un_estado_valido_y_distinto_de_los_otros_tres() -> None:
    """Caso 1. El cuarto estado existe y es propio.

    Que además no se *comporte* como `NO_CONECTADO` es lo que prueba
    `test_un_intento_fallido_no_saca_a_una_pendiente_de_pendiente`, que es donde la
    distinción tiene consecuencias.
    """
    assert EstadoDeConexion("PENDIENTE") is EstadoDeConexion.PENDIENTE
    assert len(set(EstadoDeConexion)) == 4


def test_registrar_crea_la_fila_con_el_estado_que_devolvio_el_proveedor() -> None:
    """Caso 2. El estado inicial lo decide el proveedor, no el agregado."""
    configuracion = _pendiente()

    assert configuracion.estado is EstadoDeConexion.PENDIENTE
    assert configuracion.esta_pendiente
    assert not configuracion.esta_conectada
    assert configuracion.detalle_estado == "Meta esta revisando el numero"
    assert configuracion.pendiente_desde == INSTANTE_FIJO


def test_conectar_sigue_creando_en_conectado_y_sin_reloj_de_espera() -> None:
    """Caso 3. La unidad anterior no cambia de comportamiento."""
    configuracion = _conectada()

    assert configuracion.estado is EstadoDeConexion.CONECTADO
    assert configuracion.pendiente_desde is None


def test_un_intento_fallido_no_saca_a_una_pendiente_de_pendiente() -> None:
    """Caso 4. La red se cayó; Meta no rechazó nada.

    Esta es la regla que evita inventar un rechazo, y con él un botón «Reconectar» para
    una solicitud que ya está en curso del otro lado.
    """
    configuracion = _pendiente()
    despues = INSTANTE_FIJO + timedelta(hours=2)

    cambio = configuracion.registrar_intento_fallido("Meta no respondio", despues)

    assert cambio is None
    assert configuracion.estado is EstadoDeConexion.PENDIENTE
    assert configuracion.verificado_en == despues
    assert configuracion.detalle_estado == "Meta no respondio"
    # El reloj de la espera no se reinicia: sigue midiendo desde que empezó.
    assert configuracion.pendiente_desde == INSTANTE_FIJO


def test_un_intento_fallido_sobre_una_conectada_si_la_baja() -> None:
    """Caso 5. Para todo lo demás el comportamiento anterior se mantiene."""
    configuracion = _conectada()

    cambio = configuracion.registrar_intento_fallido("Sin ruta al host", INSTANTE_FIJO)

    assert cambio is not None
    assert configuracion.estado is EstadoDeConexion.NO_CONECTADO


def test_actualizar_parametros_fusiona_sin_borrar_lo_anterior() -> None:
    """Caso 6. Una verificación parcial no puede borrar lo que identifica la cuenta."""
    configuracion = _pendiente()
    configuracion.parametros = {"phone_number_id": "123", "waba_id": "456"}

    configuracion.actualizar_parametros({"display_name": "Panaderia", "waba_id": "456"})

    assert configuracion.parametros == {
        "phone_number_id": "123",
        "waba_id": "456",
        "display_name": "Panaderia",
    }


def test_actualizar_parametros_con_nada_no_toca_la_fila() -> None:
    configuracion = _pendiente()
    configuracion.parametros = {"phone_number_id": "123"}

    configuracion.actualizar_parametros({})

    assert configuracion.parametros == {"phone_number_id": "123"}


def test_salir_de_pendiente_apaga_el_reloj_de_la_espera() -> None:
    configuracion = _pendiente()

    configuracion.registrar_verificacion(
        EstadoDeConexion.CONECTADO, None, INSTANTE_FIJO + timedelta(days=1)
    )

    assert configuracion.pendiente_desde is None


def test_volver_a_pendiente_reinicia_el_reloj() -> None:
    """Reconectar manda el número de nuevo a revisión: la espera empieza otra vez."""
    configuracion = _conectada()
    despues = INSTANTE_FIJO + timedelta(days=30)

    configuracion.registrar_verificacion(EstadoDeConexion.PENDIENTE, None, despues)

    assert configuracion.pendiente_desde == despues


def test_la_espera_vence_recien_pasado_el_maximo() -> None:
    """Caso 20. Siete días es más del doble del techo de 72 h que da RN-02."""
    configuracion = _pendiente()

    assert not configuracion.espera_vencida(INSTANTE_FIJO + timedelta(days=6), 7)
    assert configuracion.espera_vencida(INSTANTE_FIJO + timedelta(days=7), 7)


def test_una_integracion_que_no_espera_a_nadie_nunca_vence() -> None:
    configuracion = _conectada()

    assert not configuracion.espera_vencida(INSTANTE_FIJO + timedelta(days=365), 7)


def test_reconectar_puede_dejar_la_integracion_en_pendiente() -> None:
    """WhatsApp vuelve a revisión al reconectar; decir «Conectado» sería mentir 72 h."""
    configuracion = _conectada()
    despues = INSTANTE_FIJO + timedelta(days=1)

    cambio = configuracion.reconectar(
        credencial=OTRA,
        ambiente=Ambiente.HOMOLOGACION,
        ahora=despues,
        estado=EstadoDeConexion.PENDIENTE,
        detalle="Meta esta revisando el numero",
    )

    assert cambio is not None
    assert cambio.nuevo is EstadoDeConexion.PENDIENTE
    assert configuracion.pendiente_desde == despues
