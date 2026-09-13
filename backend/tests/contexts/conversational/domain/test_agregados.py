"""Los tres agregados del canal, sin red y sin base (HU-E8-*, HU-E9-*).

Lo que se fija acá son las afirmaciones que las historias hacen sobre la **forma** del modelo,
y que un refactor podría romper sin que nada más se queje:

1. **`EstadoConversacion` tiene dos valores y no tres.** HU-E9-01 RN-01 es explícita: «los
   estados son únicamente ACTIVA y ARCHIVADA», y que un hilo esté escalado se deriva de que
   exista un escalamiento abierto. Un `ESCALADA` sería el mismo hecho guardado dos veces, y el
   día que discreparan el agente contestaría encima de un operador.

2. **Un escalamiento resuelto no vuelve** (HU-E9-02 RN-04). La transición ausente es la que lo
   hace cierto.

3. **El estado de entrega sólo avanza.** WhatsApp manda los callbacks por su cuenta y no
   garantiza el orden: sin este piso, un `entregado` que llega tarde pisaría un `leído` que ya
   había llegado, y la pantalla diría que el cliente no leyó algo que leyó.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cheatsheet.contexts.conversational.domain.conversacion import (
    INTENTOS_ANTES_DE_ESCALAR,
    Conversacion,
    DireccionMensaje,
    EstadoConversacion,
    EstadoEntrega,
    Intencion,
    Mensaje,
    OrigenDelMensaje,
    TipoContenido,
)
from cheatsheet.contexts.conversational.domain.escalamiento import (
    MOTIVO_BAJA_CONFIANZA,
    Escalamiento,
    EstadoEscalamiento,
)
from cheatsheet.contexts.conversational.domain.faq import (
    FAQ,
    MENSAJE_CAMPOS_OBLIGATORIOS,
    UMBRAL_DE_SIMILITUD,
    CoincidenciaDeFAQ,
)
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

AHORA = datetime(2026, 9, 8, 15, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())


def una_conversacion(**cambios: object) -> Conversacion:
    base: dict[str, object] = {
        "id": uuid4(),
        "empresa_id": EMPRESA,
        "cliente_id": uuid4(),
        "created_at": AHORA,
    }
    base.update(cambios)
    return Conversacion(**base)  # type: ignore[arg-type]


def un_escalamiento(**cambios: object) -> Escalamiento:
    base: dict[str, object] = {
        "id": uuid4(),
        "conversacion_id": uuid4(),
        "empresa_id": EMPRESA,
        "motivo": MOTIVO_BAJA_CONFIANZA,
        "created_at": AHORA,
        "updated_at": AHORA,
    }
    base.update(cambios)
    return Escalamiento(**base)  # type: ignore[arg-type]


def una_faq(**cambios: object) -> FAQ:
    base: dict[str, object] = {
        "id": uuid4(),
        "empresa_id": EMPRESA,
        "pregunta": "¿Cuánto sale un corte?",
        "respuesta": "Un corte sale $8000.",
        "created_at": AHORA,
        "updated_at": AHORA,
    }
    base.update(cambios)
    return FAQ(**base)  # type: ignore[arg-type]


def _estado(uno: Escalamiento) -> EstadoEscalamiento:
    """Lee el estado sin que mypy lo estreche al literal del constructor."""
    return uno.estado


class TestConversacion:
    def test_los_estados_son_dos_y_no_hay_un_escalada(self) -> None:
        """HU-E9-01 RN-01, palabra por palabra."""
        assert set(EstadoConversacion.__members__) == {"ACTIVA", "ARCHIVADA"}
        # Y la conversación tampoco tiene un booleano que diga lo mismo.
        assert not hasattr(una_conversacion(), "escalada")

    def test_el_contador_se_reinicia_con_un_mensaje_entendido(self) -> None:
        # Alguien que preguntó algo raro y después preguntó bien no arrastra el error.
        hilo = una_conversacion()
        hilo.anotar_intento_fallido()
        hilo.anotar_intento_fallido()
        hilo.anotar_intento_entendido()

        assert hilo.contador == 0
        assert not hilo.agoto_los_intentos

    def test_agota_los_intentos_al_llegar_al_tope(self) -> None:
        """El «tras varios intentos» de HU-E8-01, quinto criterio."""
        hilo = una_conversacion()
        for _ in range(INTENTOS_ANTES_DE_ESCALAR):
            hilo.anotar_intento_fallido()

        assert hilo.agoto_los_intentos

    def test_rechaza_un_tope_menor_a_uno(self) -> None:
        # Con cero, el primer mensaje del cliente escalaría antes de leerse.
        with pytest.raises(EntradaInvalida):
            una_conversacion(ventana_maximo=0)

    def test_archivar_es_final(self) -> None:
        hilo = una_conversacion()
        hilo.archivar()

        assert hilo.estado is EstadoConversacion.ARCHIVADA
        with pytest.raises(InvarianteViolada):
            hilo.archivar()


class TestMensaje:
    def test_un_saliente_sin_origen_no_se_puede_pintar_y_se_rechaza(self) -> None:
        """HU-E9-01 RN-04: sin la marca, la pantalla no puede distinguir agente de operador."""
        with pytest.raises(EntradaInvalida):
            Mensaje(
                id=uuid4(),
                conversacion_id=uuid4(),
                empresa_id=EMPRESA,
                direccion=DireccionMensaje.SALIENTE,
                tipo_contenido=TipoContenido.TEXTO,
                contenido="hola",
                momento=AHORA,
            )

    def test_un_entrante_no_necesita_origen(self) -> None:
        # Lo escribió el cliente: no hay nada que distinguir.
        entrante = Mensaje(
            id=uuid4(),
            conversacion_id=uuid4(),
            empresa_id=EMPRESA,
            direccion=DireccionMensaje.ENTRANTE,
            tipo_contenido=TipoContenido.TEXTO,
            contenido="hola",
            momento=AHORA,
        )

        assert entrante.origen is None

    def test_el_estado_de_entrega_solo_avanza(self) -> None:
        """Un `entregado` que llega tarde no pisa un `leído` que ya había llegado."""
        mensaje = Mensaje(
            id=uuid4(),
            conversacion_id=uuid4(),
            empresa_id=EMPRESA,
            direccion=DireccionMensaje.SALIENTE,
            tipo_contenido=TipoContenido.TEXTO,
            contenido="hola",
            momento=AHORA,
            origen=OrigenDelMensaje.AGENTE,
        )

        mensaje.marcar_entrega(EstadoEntrega.ENVIADO)
        mensaje.marcar_entrega(EstadoEntrega.LEIDO)
        mensaje.marcar_entrega(EstadoEntrega.ENTREGADO)

        assert mensaje.estado_entrega is EstadoEntrega.LEIDO

    def test_la_intencion_es_del_mensaje_y_no_del_hilo(self) -> None:
        """El DER le da la columna a `mensaje`, y tiene razón: un hilo puede cambiar de tema."""
        assert "intencion" in Mensaje.__slots__
        assert "intencion" not in Conversacion.__slots__
        assert Intencion.DESCONOCIDA in Intencion


class TestEscalamiento:
    def test_tomar_lo_asigna_y_calla_al_agente(self) -> None:
        uno = un_escalamiento()
        operador = UsuarioId(uuid4())

        uno.tomar(operador, AHORA)

        assert _estado(uno) is EstadoEscalamiento.ASIGNADO
        assert uno.usuario_asignado_id == operador
        # Mientras esté abierto, el agente no contesta ese hilo (RN-02).
        assert uno.esta_abierto

    def test_un_escalamiento_resuelto_no_se_reabre(self) -> None:
        """HU-E9-02 RN-04. La transición ausente es la que lo hace cierto."""
        uno = un_escalamiento()
        uno.resolver(AHORA)

        assert not uno.esta_abierto
        with pytest.raises(InvarianteViolada):
            uno.tomar(UsuarioId(uuid4()), AHORA)

    def test_se_puede_resolver_sin_tomarlo(self) -> None:
        # Un operador puede leer el hilo, ver que el cliente se resolvió solo, y cerrar.
        # Obligar a tomarlo primero sería un paso que no protege nada.
        uno = un_escalamiento()
        uno.resolver(AHORA)

        assert _estado(uno) is EstadoEscalamiento.RESUELTO

    def test_no_se_toma_dos_veces(self) -> None:
        uno = un_escalamiento()
        uno.tomar(UsuarioId(uuid4()), AHORA)

        with pytest.raises(InvarianteViolada):
            uno.tomar(UsuarioId(uuid4()), AHORA)

    def test_rechaza_un_escalamiento_sin_motivo(self) -> None:
        # Un escalamiento sin motivo le llega a un operador que tiene que leer el hilo entero
        # para saber por qué está ahí.
        with pytest.raises(EntradaInvalida):
            un_escalamiento(motivo="   ")


class TestFAQ:
    def test_rechaza_pregunta_o_respuesta_vacia_con_la_frase_de_la_historia(self) -> None:
        for cambio in ({"pregunta": "  "}, {"respuesta": ""}):
            with pytest.raises(EntradaInvalida) as fallo:
                una_faq(**cambio)
            assert str(fallo.value) == MENSAJE_CAMPOS_OBLIGATORIOS

    def test_nace_obsoleta_y_con_cero_usos(self) -> None:
        """Primer criterio de HU-E9-04, más lo que el vector todavía no tiene."""
        faq = una_faq()

        assert faq.usos == 0
        assert faq.embedding_obsoleto

    def test_editar_la_pregunta_invalida_el_vector_y_editar_la_respuesta_no(self) -> None:
        """El vector se calcula sobre la pregunta: recalcularlo por la respuesta es gastar
        plata y una llamada de red por nada."""
        faq = una_faq()
        faq.marcar_indexada("modelo-v1", AHORA)

        faq.editar(pregunta=faq.pregunta, respuesta="Ahora sale $9000.", momento=AHORA)
        assert not faq.embedding_obsoleto

        faq.editar(pregunta="¿Qué precio tiene un corte?", respuesta=faq.respuesta, momento=AHORA)
        assert faq.embedding_obsoleto

    def test_editar_valida_los_campos_obligatorios(self) -> None:
        faq = una_faq()

        with pytest.raises(EntradaInvalida) as fallo:
            faq.editar(pregunta="", respuesta="algo", momento=AHORA)
        assert str(fallo.value) == MENSAJE_CAMPOS_OBLIGATORIOS

    def test_el_uso_se_cuenta_de_a_uno(self) -> None:
        faq = una_faq()
        faq.registrar_uso()
        faq.registrar_uso()

        assert faq.usos == 2

    def test_el_umbral_decide_si_una_coincidencia_alcanza(self) -> None:
        """RN-03: por debajo, el agente ofrece un asesor en lugar de contestar cualquier cosa."""
        justo = CoincidenciaDeFAQ(faq=una_faq(), similitud=UMBRAL_DE_SIMILITUD)
        apenas_menos = CoincidenciaDeFAQ(faq=una_faq(), similitud=UMBRAL_DE_SIMILITUD - 0.01)

        assert justo.alcanza
        assert not apenas_menos.alcanza
