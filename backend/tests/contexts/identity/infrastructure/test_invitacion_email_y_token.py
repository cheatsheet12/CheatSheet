"""The invitation's two adapters: the token and the email.

Cases 26 to 28 and 31 of the plan. **Nothing here opens a socket.** The console adapter
is real and writes to the log; the SMTP one is exercised against a stubbed
`aiosmtplib.send`, which is the seam where the network would be.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import aiosmtplib
import pytest
from cheatsheet.contexts.identity.application.errors import EnvioDeEmailFallido
from cheatsheet.contexts.identity.application.ports import MensajeDeInvitacion
from cheatsheet.contexts.identity.domain.valores import Email
from cheatsheet.contexts.identity.infrastructure import email_invitacion
from cheatsheet.contexts.identity.infrastructure.email_invitacion import (
    ConfiguracionSMTP,
    EnviadorDeConsola,
    EnviadorSMTP,
)
from cheatsheet.contexts.identity.infrastructure.tokens_invitacion import (
    TokenDeInvitacionAleatorio,
)

from tests.conftest import INSTANTE_FIJO


class LoggerEspia:
    """Records the structured events instead of rendering them.

    Substituted for the module's logger rather than captured through structlog: the
    pipeline is built with `cache_logger_on_first_use`, so a logger bound at import time
    ignores any later reconfiguration — and a test that depends on which file ran first
    is worse than no test.
    """

    def __init__(self) -> None:
        self.eventos: list[tuple[str, dict[str, Any]]] = []

    def info(self, evento: str, **kwargs: Any) -> None:
        self.eventos.append((evento, kwargs))

    def warning(self, evento: str, **kwargs: Any) -> None:
        self.eventos.append((evento, kwargs))


@pytest.fixture
def registros(monkeypatch) -> LoggerEspia:
    espia = LoggerEspia()
    monkeypatch.setattr(email_invitacion, "logger", espia)
    return espia


TOKEN = "un-token-de-invitacion-de-prueba"
TIMEOUT = 7


def _mensaje() -> MensajeDeInvitacion:
    return MensajeDeInvitacion(
        destinatario=Email("nuevo@empresa.com"),
        nombre_de_empresa="Panaderia Dona Rosa",
        invitado_por="Ana Perez",
        token=TOKEN,
        expira_en=INSTANTE_FIJO + timedelta(days=7),
    )


def _config() -> ConfiguracionSMTP:
    return ConfiguracionSMTP(
        host="smtp.example.test",
        puerto=587,
        usuario="usuario",
        contrasena="fake-secret-for-tests",
        remitente="no-reply@cheatsheet.test",
        usar_tls=True,
        timeout_segundos=TIMEOUT,
        url_base_de_la_app="https://app.cheatsheet.test",
    )


# ------------------------------------------------------------------- caso 26: el token


def test_el_token_de_invitacion_no_se_puede_recuperar_del_hash():
    """The real digest, unlike the test double, is one-way."""
    adaptador = TokenDeInvitacionAleatorio()
    token = adaptador.emitir()

    huella = adaptador.hashear(token)

    assert token not in huella
    assert len(huella) == 64  # SHA-256 in hex
    assert huella == adaptador.hashear(token)


def test_cada_token_de_invitacion_es_distinto_e_impredecible():
    adaptador = TokenDeInvitacionAleatorio()

    emitidos = {adaptador.emitir() for _ in range(50)}

    assert len(emitidos) == 50
    assert all(len(valor) >= 32 for valor in emitidos)


# --------------------------------------------------------- caso 27: la consola no sale


@pytest.mark.asyncio
async def test_el_adaptador_de_consola_no_abre_ningun_socket(monkeypatch):
    """If it reached the network, this stub would be what it called."""

    async def prohibido(*args: object, **kwargs: object) -> None:
        raise AssertionError("el adaptador de consola no debe usar la red")

    monkeypatch.setattr(aiosmtplib, "send", prohibido)

    await EnviadorDeConsola("https://app.cheatsheet.test").enviar_invitacion(_mensaje())


@pytest.mark.asyncio
async def test_el_adaptador_de_consola_imprime_el_enlace_completo(registros):
    """Printing it *is* its job: without a mail server there has to be some way to
    finish the flow locally.

    Asserted on the captured event rather than on stdout: the rendered output depends on
    whatever log level the rest of the suite happened to configure, and a test that
    passes or fails by ordering is worse than no test.
    """
    await EnviadorDeConsola("https://app.cheatsheet.test/").enviar_invitacion(_mensaje())

    evento, datos = registros.eventos[0]
    assert evento == "invitacion_no_enviada_modo_consola"
    assert datos["enlace"] == f"https://app.cheatsheet.test/invitacion/{TOKEN}"


# ---------------------------------------------------- caso 28: timeout y fallo del SMTP


@pytest.mark.asyncio
async def test_el_adaptador_smtp_aplica_el_timeout_configurado(monkeypatch):
    """CLAUDE.md §5: every outbound call carries an explicit timeout."""
    llamadas: list[dict[str, Any]] = []

    async def falso_send(mensaje: object, **kwargs: Any) -> None:
        llamadas.append(kwargs)

    monkeypatch.setattr(aiosmtplib, "send", falso_send)

    await EnviadorSMTP(_config()).enviar_invitacion(_mensaje())

    assert llamadas[0]["timeout"] == TIMEOUT
    assert llamadas[0]["hostname"] == "smtp.example.test"
    assert llamadas[0]["start_tls"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "excepcion",
    [aiosmtplib.SMTPConnectError("caido"), TimeoutError("tarde"), OSError("sin ruta")],
    ids=["smtp", "timeout", "socket"],
)
async def test_un_fallo_de_smtp_se_traduce_a_un_error_del_dominio(monkeypatch, excepcion):
    """The task above is what decides whether to retry, so the failure has to arrive as
    something it can name."""

    async def falso_send(mensaje: object, **kwargs: Any) -> None:
        raise excepcion

    monkeypatch.setattr(aiosmtplib, "send", falso_send)

    with pytest.raises(EnvioDeEmailFallido):
        await EnviadorSMTP(_config()).enviar_invitacion(_mensaje())


# ------------------------------------------------- caso 31: la plantilla y el logueo


def test_la_plantilla_lleva_el_enlace_y_los_datos_de_quien_invita():
    texto = email_invitacion._render("invitacion.txt", _mensaje(), "https://app.cheatsheet.test")

    assert f"https://app.cheatsheet.test/invitacion/{TOKEN}" in texto
    assert "Panaderia Dona Rosa" in texto
    assert "Ana Perez" in texto


@pytest.mark.asyncio
async def test_el_adaptador_smtp_no_registra_el_token_en_el_log(monkeypatch, registros):
    """A live invitation link in an aggregated log is an account waiting to be taken."""

    async def falso_send(mensaje: object, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(aiosmtplib, "send", falso_send)

    await EnviadorSMTP(_config()).enviar_invitacion(_mensaje())

    assert registros.eventos  # it did log something — otherwise this proves nothing
    assert TOKEN not in str(registros.eventos)


@pytest.mark.asyncio
async def test_un_fallo_de_smtp_tampoco_registra_el_token(monkeypatch, registros):
    async def falso_send(mensaje: object, **kwargs: Any) -> None:
        raise aiosmtplib.SMTPConnectError("caido")

    monkeypatch.setattr(aiosmtplib, "send", falso_send)

    with pytest.raises(EnvioDeEmailFallido):
        await EnviadorSMTP(_config()).enviar_invitacion(_mensaje())

    assert registros.eventos
    assert TOKEN not in str(registros.eventos)


def test_el_correo_lleva_texto_plano_y_html():
    """A text/plain alternative is not decoration: a client that refuses HTML still has
    to show a working link."""
    correo = email_invitacion._armar(_mensaje(), _config())

    tipos = {parte.get_content_type() for parte in correo.walk()}
    assert "text/plain" in tipos
    assert "text/html" in tipos
    assert correo["To"] == "nuevo@empresa.com"
