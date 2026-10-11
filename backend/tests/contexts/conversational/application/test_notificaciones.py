"""`NotificarAlCliente` — el aviso de un turno, guardado como mensaje del sistema (U7, D-U7-4).

Lo que `scheduling` manda por el panel (cancelar, reprogramar, confirmar) pasa a quedar en la
conversación del cliente como un `Mensaje` `SALIENTE`/`SISTEMA`. Seis afirmaciones:

1. Con o sin hilo, el aviso queda en **un** hilo activo (caso 23).
2. Si Meta falla, el mensaje queda `FALLIDO` con su motivo y **no se levanta** (caso 24).
3. Sin canal conectado no se crea ni hilo ni mensaje (caso 25a).
4. Si el mensaje no se puede guardar, el aviso igual se dio por enviado y no se levanta (caso 25).
5. El agente contesta en el mismo hilo cuando el cliente responde, y el modelo no ve el texto del
   aviso (casos 26 y 27).
6. Ningún log lleva el teléfono, el nombre ni el texto (caso 28).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.conversational.application.errors import (
    CanalNoConectado,
    EnvioIncierto,
    MensajeRechazado,
    MensajeriaSaturada,
)
from cheatsheet.contexts.conversational.application.notificaciones import (
    EnvioDeAviso,
    NotificarAlCliente,
    PlantillaDeAviso,
    ResultadoDeNotificacion,
)
from cheatsheet.contexts.conversational.domain.conversacion import (
    Conversacion,
    DireccionMensaje,
    EstadoConversacion,
    EstadoEntrega,
    Intencion,
    OrigenDelMensaje,
)
from cheatsheet.shared.empresa import EmpresaId
from structlog.testing import capture_logs

from tests.contexts.conversational.application.dobles import (
    RepositorioConversacionEnMemoria,
    RepositorioMensajeEnMemoria,
    sin_savepoint,
)
from tests.contexts.conversational.application.escena import (
    EMPRESA as EMPRESA_DE_LA_ESCENA,
)
from tests.contexts.conversational.application.escena import TELEFONO as TELEFONO_DE_LA_ESCENA
from tests.contexts.conversational.application.escena import Escena, leyendo

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
TELEFONO = "5491112345678"
TEXTO = "Hola Ana Diaz, tu turno de Corte del 15/10/2026 a las 10:30 fue cancelado."


class Canal:
    """Un `PortMensajeria` programable: manda, guarda lo que salió, o levanta lo que se le diga."""

    def __init__(self, *, falla: Exception | None = None) -> None:
        self.textos: list[tuple[str, str]] = []
        self.plantillas: list[tuple[str, str, str, dict[str, str]]] = []
        self.falla = falla

    async def enviar(self, *, telefono: str, texto: str) -> str:
        if self.falla is not None:
            raise self.falla
        self.textos.append((telefono, texto))
        return "wamid.TEXTO"

    async def enviar_plantilla(
        self, *, telefono: str, nombre: str, idioma: str, parametros: Mapping[str, str]
    ) -> str:
        if self.falla is not None:
            raise self.falla
        self.plantillas.append((telefono, nombre, idioma, dict(parametros)))
        return "wamid.PLANTILLA"


def _caso(
    canal: Canal,
    conversaciones: RepositorioConversacionEnMemoria | None = None,
    mensajes: RepositorioMensajeEnMemoria | None = None,
) -> tuple[NotificarAlCliente, RepositorioConversacionEnMemoria, RepositorioMensajeEnMemoria]:
    conversaciones = conversaciones or RepositorioConversacionEnMemoria()
    mensajes = mensajes or RepositorioMensajeEnMemoria()
    caso = NotificarAlCliente(
        conversaciones=conversaciones,
        mensajes=mensajes,
        mensajeria=canal,
        aislar=sin_savepoint,
    )
    return caso, conversaciones, mensajes


async def _avisar(
    caso: NotificarAlCliente, cliente_id: UUID, envio: EnvioDeAviso | None = None
) -> ResultadoDeNotificacion:
    return await caso.ejecutar(
        empresa_id=EMPRESA,
        cliente_id=cliente_id,
        telefono=TELEFONO,
        envio=envio or EnvioDeAviso(texto=TEXTO),
        ahora=AHORA,
    )


class TestElHilo:
    async def test_sin_conversacion_se_crea_una_activa_y_el_aviso_queda_en_ella(self) -> None:
        """**Caso 23 (a) y caso 3.** Antes el aviso no dejaba ningún registro."""
        cliente = uuid4()
        caso, conversaciones, mensajes = _caso(Canal())

        resultado = await _avisar(caso, cliente)

        (hilo,) = conversaciones.hilos.values()
        assert (hilo.cliente_id, hilo.estado) == (cliente, EstadoConversacion.ACTIVA)
        assert hilo.ultimo_mensaje_en == AHORA
        (aviso,) = mensajes.mensajes.values()
        assert aviso.conversacion_id == hilo.id
        assert (aviso.direccion, aviso.origen) == (
            DireccionMensaje.SALIENTE,
            OrigenDelMensaje.SISTEMA,
        )
        assert (aviso.contenido, aviso.externo_id) == (TEXTO, "wamid.TEXTO")
        assert aviso.estado_entrega is EstadoEntrega.ENVIADO
        assert (resultado.enviado, resultado.externo_id, resultado.falla) == (
            True,
            "wamid.TEXTO",
            None,
        )
        assert (resultado.sin_registrar, resultado.causa) == (False, None)

    async def test_con_una_conversacion_activa_se_agrega_ahi(self) -> None:
        """**Caso 23 (b).**"""
        cliente = uuid4()
        activa = Conversacion(id=uuid4(), empresa_id=EMPRESA, cliente_id=cliente, created_at=AHORA)
        caso, conversaciones, mensajes = _caso(Canal(), RepositorioConversacionEnMemoria(activa))

        await _avisar(caso, cliente)

        assert list(conversaciones.hilos) == [activa.id]
        (aviso,) = mensajes.mensajes.values()
        assert aviso.conversacion_id == activa.id

    async def test_con_una_conversacion_archivada_se_crea_otra(self) -> None:
        """**Caso 23 (c).** Un hilo archivado no se desarchiva (`Conversacion.archivar`)."""
        cliente = uuid4()
        vieja = Conversacion(id=uuid4(), empresa_id=EMPRESA, cliente_id=cliente, created_at=AHORA)
        vieja.archivar()
        caso, conversaciones, mensajes = _caso(Canal(), RepositorioConversacionEnMemoria(vieja))

        await _avisar(caso, cliente)

        assert len(conversaciones.hilos) == 2
        (aviso,) = mensajes.mensajes.values()
        assert aviso.conversacion_id != vieja.id
        assert conversaciones.hilos[aviso.conversacion_id].estado is EstadoConversacion.ACTIVA

    async def test_el_hilo_se_pide_bloqueado_como_hace_el_agente(self) -> None:
        """T10: un mensaje del cliente que llega a la vez no abre un segundo hilo activo."""
        caso, conversaciones, _ = _caso(Canal())

        await _avisar(caso, uuid4())

        assert conversaciones.bloqueos == [True]


class TestLaPlantilla:
    async def test_una_plantilla_aprobada_sale_como_plantilla_y_se_guarda_su_texto(self) -> None:
        canal = Canal()
        caso, _, mensajes = _caso(canal)
        envio = EnvioDeAviso(
            texto=TEXTO,
            plantilla=PlantillaDeAviso(
                nombre="turno_cancelado", idioma="es_AR", parametros={"nombre": "Ana Diaz"}
            ),
        )

        await _avisar(caso, uuid4(), envio)

        assert canal.textos == []
        assert canal.plantillas == [(TELEFONO, "turno_cancelado", "es_AR", {"nombre": "Ana Diaz"})]
        (aviso,) = mensajes.mensajes.values()
        assert (aviso.contenido, aviso.externo_id) == (TEXTO, "wamid.PLANTILLA")

    async def test_el_wamid_que_no_entra_en_la_columna_se_guarda_como_none(self) -> None:
        """H3: un id vacío o demasiado largo no se corta (el aviso igual salió)."""

        class CanalConIdLargo(Canal):
            async def enviar(self, *, telefono: str, texto: str) -> str:
                del telefono, texto
                return "w" * 400

        caso, _, mensajes = _caso(CanalConIdLargo())

        resultado = await _avisar(caso, uuid4())

        (aviso,) = mensajes.mensajes.values()
        assert aviso.externo_id is None
        assert aviso.estado_entrega is EstadoEntrega.ENVIADO
        assert resultado.externo_id is None


class TestCuandoElCanalFalla:
    @pytest.mark.parametrize(
        ("falla", "motivo"),
        [
            (MensajeRechazado("no", codigo=131047), "131047"),
            (MensajeriaSaturada("saturada"), "SATURADA"),
            (EnvioIncierto("sin respuesta"), "INCIERTO"),
            (RuntimeError(f"falló {TELEFONO}"), "ERROR"),
        ],
    )
    async def test_el_mensaje_queda_fallido_con_su_motivo_y_no_levanta(
        self, falla: Exception, motivo: str
    ) -> None:
        """**Caso 24.** El turno queda cancelado; el operador ve el aviso `FALLIDO` en el hilo."""
        caso, conversaciones, mensajes = _caso(Canal(falla=falla))

        resultado = await _avisar(caso, uuid4())

        (aviso,) = mensajes.mensajes.values()
        assert aviso.estado_entrega is EstadoEntrega.FALLIDO
        assert (aviso.motivo_de_falla, aviso.externo_id) == (motivo, None)
        assert aviso.contenido == TEXTO
        assert len(conversaciones.hilos) == 1
        assert (resultado.enviado, resultado.falla) == (False, motivo)

    @pytest.mark.parametrize(
        ("falla", "transitoria"),
        [
            (MensajeriaSaturada("saturada"), True),
            (EnvioIncierto("sin respuesta"), False),
            (MensajeRechazado("no", codigo=131047), False),
            (CanalNoConectado("sin WhatsApp"), False),
            (RuntimeError("falló"), False),
        ],
    )
    async def test_solo_la_saturacion_es_transitoria(
        self, falla: Exception, transitoria: bool
    ) -> None:
        """**Caso 28.** El mismo criterio que `api/fallas_de_canal._traducir` (U8, P1)."""
        caso, _, _ = _caso(Canal(falla=falla))

        resultado = await _avisar(caso, uuid4())

        assert resultado.transitoria is transitoria

    async def test_un_envio_que_salio_no_es_transitorio(self) -> None:
        caso, _, _ = _caso(Canal())

        resultado = await _avisar(caso, uuid4())

        assert (resultado.enviado, resultado.transitoria) == (True, False)

    async def test_sin_canal_conectado_no_se_crea_ni_hilo_ni_mensaje(self) -> None:
        """**Caso 25a.** La empresa no usa el canal: llenarle la bandeja de avisos fallidos es ruido."""
        caso, conversaciones, mensajes = _caso(Canal(falla=CanalNoConectado("sin WhatsApp")))

        resultado = await _avisar(caso, uuid4())

        assert conversaciones.hilos == {}
        assert mensajes.mensajes == {}
        assert (resultado.enviado, resultado.falla) == (False, "SIN_CANAL")

    async def test_sin_canal_tampoco_toca_un_hilo_existente(self) -> None:
        cliente = uuid4()
        activa = Conversacion(id=uuid4(), empresa_id=EMPRESA, cliente_id=cliente, created_at=AHORA)
        caso, _, mensajes = _caso(
            Canal(falla=CanalNoConectado("sin WhatsApp")), RepositorioConversacionEnMemoria(activa)
        )

        await _avisar(caso, cliente)

        assert mensajes.mensajes == {}
        assert activa.ultimo_mensaje_en is None


class TestCuandoNoSePuedeGuardar:
    async def test_el_aviso_salio_y_no_se_levanta(self) -> None:
        """**Caso 25.** El envío a Meta ya ocurrió y no se repite; el turno sigue cancelado."""

        class MensajesQueNoGuardan(RepositorioMensajeEnMemoria):
            async def agregar(self, mensaje: object) -> None:
                del mensaje
                raise RuntimeError(f"la base rechazó {TELEFONO}")

        canal = Canal()
        caso, _, _ = _caso(canal, mensajes=MensajesQueNoGuardan())

        resultado = await _avisar(caso, uuid4())

        assert len(canal.textos) == 1
        assert resultado.enviado is True
        assert resultado.sin_registrar is True
        assert resultado.externo_id == "wamid.TEXTO"
        # S1: la causa es sólo la clase de la excepción; el texto trae el teléfono.
        assert resultado.causa == "RuntimeError"
        assert TELEFONO not in repr(resultado)

    async def test_la_escritura_corre_dentro_del_savepoint_que_le_pasan(self) -> None:
        eventos: list[str] = []

        @asynccontextmanager
        async def aislar() -> AsyncIterator[None]:
            eventos.append("abre")
            try:
                yield
            finally:
                eventos.append("cierra")

        conversaciones = RepositorioConversacionEnMemoria()
        mensajes = RepositorioMensajeEnMemoria()
        caso = NotificarAlCliente(
            conversaciones=conversaciones,
            mensajes=mensajes,
            mensajeria=Canal(),
            aislar=aislar,
        )

        await _avisar(caso, uuid4())

        assert eventos == ["abre", "cierra"]
        assert len(mensajes.mensajes) == 1

    async def test_un_savepoint_que_se_deshace_no_levanta(self) -> None:
        @asynccontextmanager
        async def aislar() -> AsyncIterator[None]:
            yield
            raise RuntimeError("el savepoint no se pudo soltar")

        caso = NotificarAlCliente(
            conversaciones=RepositorioConversacionEnMemoria(),
            mensajes=RepositorioMensajeEnMemoria(),
            mensajeria=Canal(),
            aislar=aislar,
        )

        resultado = await _avisar(caso, uuid4())

        assert resultado.sin_registrar is True
        assert resultado.causa == "RuntimeError"


class TestElAgenteRespondeEnElMismoHilo:
    async def test_la_respuesta_a_un_aviso_se_procesa_en_el_hilo_del_aviso(self) -> None:
        """**Caso 27 (RN-03) y caso 26.** Y el modelo ve el descriptor, no el texto del aviso."""
        escena = Escena(lectura=leyendo(Intencion.FAQ), conocido=True)
        caso = NotificarAlCliente(
            conversaciones=escena.conversaciones,
            mensajes=escena.mensajes,
            mensajeria=Canal(),
            aislar=sin_savepoint,
        )
        await caso.ejecutar(
            empresa_id=EMPRESA_DE_LA_ESCENA,
            cliente_id=escena.cliente_id,
            telefono=TELEFONO_DE_LA_ESCENA,
            envio=EnvioDeAviso(texto=TEXTO),
            ahora=escena.ahora,
        )
        (hilo_del_aviso,) = escena.conversaciones.hilos.values()

        respuesta = await escena.procesar("sí, voy")

        assert respuesta.conversacion_id == hilo_del_aviso.id
        assert len(escena.conversaciones.hilos) == 1
        [historial] = escena.interprete.historiales
        assert historial == ["[Aviso automático del negocio sobre un turno]", "sí, voy"]
        assert "Ana Diaz" not in repr(escena.interprete.historiales)


class TestLosLogs:
    async def test_ningun_log_lleva_el_telefono_el_nombre_ni_el_texto(self) -> None:
        """**Caso 28 (avisos).**"""
        with capture_logs() as registros:
            for canal in (
                Canal(),
                Canal(falla=MensajeRechazado(f"rechazo {TELEFONO}", codigo=131047)),
                Canal(falla=CanalNoConectado("sin WhatsApp")),
            ):
                caso, _, _ = _caso(canal)
                await _avisar(caso, uuid4())

        volcado = repr(registros)
        for dato in (TELEFONO, "Ana Diaz", TEXTO):
            assert dato not in volcado
