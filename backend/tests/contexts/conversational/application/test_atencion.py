"""`ResponderComoOperador` — el destino del mensaje del operador (HU-E9-01).

**Lo que este archivo fija es que el operador no elige a quién le escribe.** El número sale del
cliente dueño del hilo, resuelto en `master_data`; no hay forma de pasarlo desde afuera. Un
Operador con un número ajeno en la mano no puede usar la cuenta de WhatsApp Business de la
empresa para escribirle a cualquiera.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cheatsheet.contexts.conversational.application.atencion import ResponderComoOperador
from cheatsheet.contexts.conversational.application.errors import ClienteSinWhatsApp
from cheatsheet.contexts.conversational.domain.conversacion import (
    Conversacion,
    EstadoEntrega,
    Mensaje,
    OrigenDelMensaje,
)
from cheatsheet.contexts.conversational.domain.escalamiento import Escalamiento
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.roles import RolUsuario

from tests.contexts.conversational.application.dobles import (
    DirectorioEnMemoria,
    MensajeriaEnMemoria,
    PublicadorEnMemoria,
    RepositorioConversacionEnMemoria,
    RepositorioEscalamientoEnMemoria,
    RepositorioMensajeEnMemoria,
)

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())
OPERADOR = UsuarioId(uuid4())
AHORA = datetime(2026, 10, 3, 15, 0, tzinfo=UTC)
TELEFONO_DEL_CLIENTE = "5491112345678"
TELEFONO_AJENO = "5491199999999"


class _Armado:
    def __init__(self, *, tomado: bool = True, con_whatsapp: bool = True) -> None:
        self.cliente_id = uuid4()
        self.directorio = DirectorioEnMemoria(
            {TELEFONO_DEL_CLIENTE: (self.cliente_id, "Maria")} if con_whatsapp else {}
        )
        self.hilo = Conversacion(
            id=uuid4(), empresa_id=EMPRESA, cliente_id=self.cliente_id, created_at=AHORA
        )
        self.escalamiento = Escalamiento(
            id=uuid4(), conversacion_id=self.hilo.id, empresa_id=EMPRESA, motivo="Pidio un asesor"
        )
        self.escalamiento.tomar(OPERADOR, AHORA)
        self.conversaciones = RepositorioConversacionEnMemoria(self.hilo)
        self.mensajes = RepositorioMensajeEnMemoria()
        # Sin tomar no hay escalamiento abierto en el hilo: el agente sigue contestando.
        self.escalamientos = RepositorioEscalamientoEnMemoria(
            *([self.escalamiento] if tomado else [])
        )
        self.mensajeria = MensajeriaEnMemoria()
        self.publicador = PublicadorEnMemoria()

    def caso_de_uso(self) -> ResponderComoOperador:
        return ResponderComoOperador(
            conversaciones=self.conversaciones,
            mensajes=self.mensajes,
            escalamientos=self.escalamientos,
            directorio=self.directorio,
            mensajeria=self.mensajeria,
            publicador=self.publicador,
        )

    async def responder(
        self, texto: str = "Hola, soy Ana", rol: RolUsuario = RolUsuario.OPERADOR
    ) -> Mensaje:
        return await self.caso_de_uso().ejecutar(
            empresa_id=EMPRESA,
            usuario_id=OPERADOR,
            rol=rol,
            conversacion_id=self.hilo.id,
            texto=texto,
            ahora=AHORA,
        )


async def test_el_mensaje_sale_al_cliente_del_hilo_y_no_a_un_numero_ajeno() -> None:
    armado = _Armado()

    await armado.responder("Hola, soy Ana")

    assert armado.mensajeria.enviados == [(TELEFONO_DEL_CLIENTE, "Hola, soy Ana")]


async def test_si_el_cliente_no_tiene_whatsapp_no_se_envia_ni_se_guarda_nada() -> None:
    armado = _Armado(con_whatsapp=False)

    with pytest.raises(ClienteSinWhatsApp, match="no tiene un WhatsApp registrado"):
        await armado.responder()

    assert armado.mensajeria.enviados == []
    assert armado.mensajes.mensajes == {}
    assert armado.publicador.eventos == []


async def test_cliente_sin_whatsapp_es_un_error_de_entrada_invalida() -> None:
    """Hereda de `EntradaInvalida`: la API lo traduce a 422."""
    assert issubclass(ClienteSinWhatsApp, EntradaInvalida)


async def test_sin_escalamiento_tomado_se_rechaza_antes_de_consultar_el_directorio() -> None:
    armado = _Armado(tomado=False)
    consultas: list[object] = []
    original = armado.directorio.telefono_de

    async def espia(cliente_id: object) -> str | None:
        consultas.append(cliente_id)
        return await original(armado.cliente_id)

    armado.directorio.telefono_de = espia  # type: ignore[method-assign]  # el espía sustituye el método del doble
    with pytest.raises(EntradaInvalida, match="tomar el escalamiento"):
        await armado.responder()

    assert consultas == []
    assert armado.mensajeria.enviados == []


async def test_un_rol_de_solo_lectura_no_puede_responder() -> None:
    armado = _Armado()

    with pytest.raises(EntradaInvalida, match="Administrador u Operador"):
        await armado.responder(rol=RolUsuario.SOLO_LECTURA)

    assert armado.mensajeria.enviados == []


async def test_un_texto_vacio_se_rechaza() -> None:
    armado = _Armado()

    with pytest.raises(EntradaInvalida, match="vacío"):
        await armado.responder("   ")

    assert armado.mensajeria.enviados == []


async def test_camino_feliz_guarda_el_mensaje_del_operador_y_audita() -> None:
    armado = _Armado()

    mensaje = await armado.responder("Hola, soy Ana")

    assert mensaje.origen is OrigenDelMensaje.OPERADOR
    assert mensaje.externo_id == "wamid-1"
    assert mensaje.estado_entrega is EstadoEntrega.ENVIADO
    assert armado.mensajes.mensajes[mensaje.id] is mensaje
    assert armado.publicador.acciones == ["responder_como_operador"]


@pytest.mark.parametrize(
    "externo_id", [pytest.param("", id="vacio"), pytest.param("w" * 161, id="demasiado-largo")]
)
async def test_un_wamid_que_no_sirve_se_guarda_como_sin_id(externo_id: str) -> None:
    armado = _Armado()
    armado.mensajeria = _CanalConId(externo_id)  # type: ignore[assignment]

    saliente = await armado.responder()

    assert saliente.externo_id is None


class _CanalConId:
    async def enviar(self, *, telefono: str, texto: str) -> str:
        del telefono, texto
        return self._externo_id

    def __init__(self, externo_id: str) -> None:
        self._externo_id = externo_id
