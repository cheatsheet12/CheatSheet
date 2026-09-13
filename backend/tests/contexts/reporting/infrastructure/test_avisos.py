"""El correo del contador y el generador del enlace (HU-E10-05).

**Ningún test de acá abre un socket.** El transporte es un doble que guarda el mensaje, que es
lo que permite afirmar lo único que importa del correo: que el asunto nombra a la empresa, que
el enlace está en el cuerpo, y que un fallo del servidor de correo **se propaga** — porque si
el mail no sale, la invitación no ocurrió.
"""

from __future__ import annotations

from datetime import UTC, datetime
from email.message import EmailMessage

import pytest
from cheatsheet.contexts.reporting.application.errors import InvitacionNoEnviada
from cheatsheet.contexts.reporting.infrastructure.acceso import EnlaceContableAleatorio
from cheatsheet.contexts.reporting.infrastructure.avisos import (
    AvisoAlContadorPorConsola,
    AvisoAlContadorPorEmail,
    crear_aviso_al_contador,
)
from cheatsheet.platform.email import ErrorDeEnvioDeEmail
from cheatsheet.platform.settings import AdaptadorDeEmail, Entorno

from tests.conftest import settings_de_prueba

VENCE = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)
ENLACE = "https://app.cheatsheet.ar/contador/abc123"


class TransporteFalso:
    def __init__(self, *, falla: bool = False) -> None:
        self.enviados: list[EmailMessage] = []
        self.falla = falla

    @property
    def remitente(self) -> str:
        return "no-responder@cheatsheet.ar"

    async def enviar(self, correo: EmailMessage) -> None:
        if self.falla:
            raise ErrorDeEnvioDeEmail("el servidor no responde")
        self.enviados.append(correo)


@pytest.mark.asyncio
async def test_el_correo_nombra_a_la_empresa_y_lleva_el_enlace() -> None:
    transporte = TransporteFalso()
    await AvisoAlContadorPorEmail(transporte).enviar_enlace(
        email="contador@estudio.com.ar",
        enlace=ENLACE,
        empresa="Ferretería Ñandú",
        vence=VENCE,
    )
    correo = transporte.enviados[0]
    assert correo["To"] == "contador@estudio.com.ar"
    assert "Ferretería Ñandú" in str(correo["Subject"])
    cuerpo = correo.get_body(preferencelist=("plain",))
    assert cuerpo is not None
    assert ENLACE in cuerpo.get_content()
    assert "05/05/2026" in cuerpo.get_content()


@pytest.mark.asyncio
async def test_si_el_transporte_falla_la_invitacion_falla() -> None:
    with pytest.raises(InvitacionNoEnviada):
        await AvisoAlContadorPorEmail(TransporteFalso(falla=True)).enviar_enlace(
            email="contador@estudio.com.ar", enlace=ENLACE, empresa="X", vence=VENCE
        )


@pytest.mark.asyncio
async def test_el_de_consola_no_abre_ningun_socket() -> None:
    await AvisoAlContadorPorConsola().enviar_enlace(
        email="contador@estudio.com.ar", enlace=ENLACE, empresa="X", vence=VENCE
    )


def test_la_eleccion_del_adaptador_sigue_a_la_configuracion() -> None:
    from dataclasses import replace

    consola = replace(
        settings_de_prueba(), email_adaptador=AdaptadorDeEmail.CONSOLA, entorno=Entorno.LOCAL
    )
    assert isinstance(
        crear_aviso_al_contador(consola, TransporteFalso()), AvisoAlContadorPorConsola
    )

    smtp = replace(settings_de_prueba(), email_adaptador=AdaptadorDeEmail.SMTP)
    assert isinstance(crear_aviso_al_contador(smtp, TransporteFalso()), AvisoAlContadorPorEmail)


class TestEnlace:
    def test_cada_enlace_es_distinto(self) -> None:
        generador = EnlaceContableAleatorio()
        assert generador.emitir() != generador.emitir()

    def test_el_hash_no_contiene_el_valor(self) -> None:
        """Lo que se guarda es el digesto: una base filtrada no da acceso a nada."""
        generador = EnlaceContableAleatorio()
        valor = generador.emitir()
        digesto = generador.hashear(valor)
        assert valor not in digesto
        assert len(digesto) == 64

    def test_el_mismo_valor_da_el_mismo_hash(self) -> None:
        """Sin esto, un enlace válido dejaría de encontrarse en la tabla."""
        generador = EnlaceContableAleatorio()
        assert generador.hashear("abc") == generador.hashear("abc")
