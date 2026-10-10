"""La raíz ata el aviso de `scheduling` con `NotificarAlCliente` de `conversational` (U7, D-U7-4).

`scheduling` ve su `CanalDeAvisos`; `conversational` ve su caso de uso. Lo único que los conoce a
los dos es `api/avisos_de_turno.py`, y es lo que se prueba: que traduce el envío y el resultado,
que el aviso queda en el hilo del cliente con la hora del reloj de la unidad y que la escritura
corre en el savepoint de la sesión.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from cheatsheet.api.agenda import armar_notificador
from cheatsheet.api.avisos_de_turno import CanalDeAvisosViaConversacion, armar_canal_de_avisos
from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.contexts.conversational.application.errors import (
    CanalNoConectado,
    EnvioIncierto,
    MensajeriaSaturada,
)
from cheatsheet.contexts.conversational.application.notificaciones import NotificarAlCliente
from cheatsheet.contexts.conversational.domain.conversacion import (
    EstadoEntrega,
    OrigenDelMensaje,
)
from cheatsheet.contexts.scheduling.infrastructure.avisos import (
    AvisoPorWhatsApp,
    EnvioParaAviso,
    PlantillaParaAviso,
)
from cheatsheet.shared.empresa import EmpresaId

from tests.contexts.conversational.application.dobles import (
    RepositorioConversacionEnMemoria,
    RepositorioMensajeEnMemoria,
    sin_savepoint,
)

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())
AHORA = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)
TELEFONO = "5491112345678"


class _Reloj:
    def ahora(self) -> datetime:
        return AHORA


class _Canal:
    def __init__(self, *, falla: Exception | None = None) -> None:
        self.plantillas: list[tuple[str, str, str, dict[str, str]]] = []
        self.textos: list[str] = []
        self.falla = falla

    async def enviar(self, *, telefono: str, texto: str) -> str:
        del telefono
        if self.falla is not None:
            raise self.falla
        self.textos.append(texto)
        return "wamid.TEXTO"

    async def enviar_plantilla(
        self, *, telefono: str, nombre: str, idioma: str, parametros: Mapping[str, str]
    ) -> str:
        if self.falla is not None:
            raise self.falla
        self.plantillas.append((telefono, nombre, idioma, dict(parametros)))
        return "wamid.PLANTILLA"


def _adaptador(
    canal: _Canal,
) -> tuple[
    CanalDeAvisosViaConversacion, RepositorioConversacionEnMemoria, RepositorioMensajeEnMemoria
]:
    conversaciones = RepositorioConversacionEnMemoria()
    mensajes = RepositorioMensajeEnMemoria()
    caso = NotificarAlCliente(
        conversaciones=conversaciones,
        mensajes=mensajes,
        mensajeria=canal,
        aislar=sin_savepoint,
    )
    return (
        CanalDeAvisosViaConversacion(caso, empresa_id=EMPRESA, reloj=_Reloj()),
        conversaciones,
        mensajes,
    )


async def test_un_texto_de_fabrica_sale_por_el_canal_y_queda_en_el_hilo_del_cliente() -> None:
    cliente = uuid4()
    adaptador, conversaciones, mensajes = _adaptador(_Canal())

    resultado = await adaptador.notificar(
        cliente_id=cliente, telefono=TELEFONO, envio=EnvioParaAviso(texto="Tu turno fue cancelado")
    )

    assert (resultado.enviado, resultado.falla, resultado.sin_registrar) == (True, None, False)
    (hilo,) = conversaciones.hilos.values()
    assert hilo.cliente_id == cliente
    assert hilo.empresa_id == EMPRESA
    (aviso,) = mensajes.mensajes.values()
    assert (aviso.origen, aviso.contenido, aviso.momento) == (
        OrigenDelMensaje.SISTEMA,
        "Tu turno fue cancelado",
        AHORA,
    )
    assert aviso.empresa_id == EMPRESA


async def test_una_plantilla_aprobada_sale_como_plantilla_y_se_guarda_su_texto() -> None:
    canal = _Canal()
    adaptador, _, mensajes = _adaptador(canal)
    envio = EnvioParaAviso(
        texto="Hola Ana, tu turno fue cancelado",
        plantilla=PlantillaParaAviso(
            nombre="turno_cancelado", idioma="es_AR", parametros={"nombre": "Ana"}
        ),
    )

    await adaptador.notificar(cliente_id=uuid4(), telefono=TELEFONO, envio=envio)

    assert canal.plantillas == [(TELEFONO, "turno_cancelado", "es_AR", {"nombre": "Ana"})]
    (aviso,) = mensajes.mensajes.values()
    assert aviso.contenido == "Hola Ana, tu turno fue cancelado"
    assert aviso.externo_id == "wamid.PLANTILLA"


async def test_un_canal_caido_se_traduce_a_un_resultado_y_el_mensaje_queda_fallido() -> None:
    adaptador, _, mensajes = _adaptador(_Canal(falla=RuntimeError("Meta caído")))

    resultado = await adaptador.notificar(
        cliente_id=uuid4(), telefono=TELEFONO, envio=EnvioParaAviso(texto="x")
    )

    assert (resultado.enviado, resultado.falla) == (False, "ERROR")
    assert resultado.causa is None
    (aviso,) = mensajes.mensajes.values()
    assert (aviso.estado_entrega, aviso.motivo_de_falla) == (EstadoEntrega.FALLIDO, "ERROR")


async def test_sin_whatsapp_conectado_el_resultado_dice_sin_canal_y_no_se_guarda_nada() -> None:
    adaptador, conversaciones, mensajes = _adaptador(
        _Canal(falla=CanalNoConectado("La empresa no conectó WhatsApp"))
    )

    resultado = await adaptador.notificar(
        cliente_id=uuid4(), telefono=TELEFONO, envio=EnvioParaAviso(texto="x")
    )

    assert (resultado.enviado, resultado.falla, resultado.sin_registrar) == (
        False,
        "SIN_CANAL",
        False,
    )
    assert conversaciones.hilos == {}
    assert mensajes.mensajes == {}


# --- El ensamblado ----------------------------------------------------------------------------------------


def _unidad(abiertos: list[str]) -> UnidadDeTrabajo:
    class _Savepoint:
        async def __aenter__(self) -> None:
            abiertos.append("abre")

        async def __aexit__(self, *_: object) -> None:
            abiertos.append("cierra")

    return UnidadDeTrabajo(
        sesion=SimpleNamespace(begin_nested=_Savepoint),  # type: ignore[arg-type]
        publicador=None,  # type: ignore[arg-type]
        reloj=_Reloj(),
    )


async def test_armar_canal_de_avisos_usa_el_savepoint_de_la_sesion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La escritura del aviso corre en `sesion.begin_nested`: un rechazo de la base no voltea el turno."""
    from cheatsheet.api import avisos_de_turno as modulo

    abiertos: list[str] = []
    conversaciones = RepositorioConversacionEnMemoria()
    mensajes = RepositorioMensajeEnMemoria()
    monkeypatch.setattr(
        modulo,
        "Conversaciones",
        SimpleNamespace(
            armar=lambda _unidad: SimpleNamespace(conversaciones=conversaciones, mensajes=mensajes)
        ),
    )
    canal = armar_canal_de_avisos(_unidad(abiertos), empresa_id=EMPRESA, canal=_Canal())

    await canal.notificar(cliente_id=uuid4(), telefono=TELEFONO, envio=EnvioParaAviso(texto="x"))

    assert abiertos == ["abre", "cierra"]
    assert len(mensajes.mensajes) == 1


async def test_armar_notificador_es_el_aviso_por_whatsapp_sobre_ese_canal() -> None:
    notificador = armar_notificador(_unidad([]), empresa_id=EMPRESA, canal=_Canal())

    assert isinstance(notificador, AvisoPorWhatsApp)


async def test_si_el_mensaje_no_se_guarda_el_resultado_lleva_la_clase_de_la_causa() -> None:
    """S1: `causa` llega a `scheduling` como la clase de la excepción, nunca su texto."""

    class MensajesQueNoGuardan(RepositorioMensajeEnMemoria):
        async def agregar(self, mensaje: object) -> None:
            del mensaje
            raise RuntimeError(f"la base rechazó {TELEFONO}")

    caso = NotificarAlCliente(
        conversaciones=RepositorioConversacionEnMemoria(),
        mensajes=MensajesQueNoGuardan(),
        mensajeria=_Canal(),
        aislar=sin_savepoint,
    )
    adaptador = CanalDeAvisosViaConversacion(caso, empresa_id=EMPRESA, reloj=_Reloj())

    resultado = await adaptador.notificar(
        cliente_id=uuid4(), telefono=TELEFONO, envio=EnvioParaAviso(texto="x")
    )

    assert (resultado.enviado, resultado.sin_registrar) == (True, True)
    assert resultado.causa == "RuntimeError"
    assert TELEFONO not in repr(resultado)


async def test_el_adaptador_propaga_si_la_falla_es_transitoria() -> None:
    """**Caso 28.** La saturación de Meta llega a `scheduling` como transitoria; el resto no."""
    saturada, _, _ = _adaptador(_Canal(falla=MensajeriaSaturada("saturada")))
    incierta, _, _ = _adaptador(_Canal(falla=EnvioIncierto("sin respuesta")))
    envio = EnvioParaAviso(texto="Tu turno")

    transitorio = await saturada.notificar(cliente_id=uuid4(), telefono=TELEFONO, envio=envio)
    definitivo = await incierta.notificar(cliente_id=uuid4(), telefono=TELEFONO, envio=envio)

    assert (transitorio.falla, transitorio.transitoria) == ("SATURADA", True)
    assert (definitivo.falla, definitivo.transitoria) == ("INCIERTO", False)
