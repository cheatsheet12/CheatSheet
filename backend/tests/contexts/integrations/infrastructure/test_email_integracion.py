"""El aviso por mail de HU-E2-03 — los dos desenlaces asíncronos.

Contra un transporte doble: lo que importa acá es **qué mensaje se arma**, no el socket,
que ya tiene su propia prueba en `platform/`. Ninguna prueba abre una conexión.
"""

from __future__ import annotations

from email.message import EmailMessage

import pytest
from cheatsheet.contexts.integrations.application.ports import AvisoDeIntegracion
from cheatsheet.contexts.integrations.domain.valores import EstadoDeConexion, SistemaExterno
from cheatsheet.contexts.integrations.infrastructure.email_integracion import AvisoPorEmail
from cheatsheet.platform.email import ErrorDeEnvioDeEmail

pytestmark = pytest.mark.asyncio

URL_BASE = "https://app.cheatsheet.test"
REMITENTE = "no-reply@cheatsheet.test"


class TransporteEspia:
    """Implements `TransporteDeEmail`. Records instead of connecting."""

    def __init__(self, *, falla: bool = False) -> None:
        self.enviados: list[EmailMessage] = []
        self.falla = falla

    @property
    def remitente(self) -> str:
        return REMITENTE

    async def enviar(self, correo: EmailMessage) -> None:
        if self.falla:
            raise ErrorDeEnvioDeEmail("el servidor no contesta")
        self.enviados.append(correo)


def _aviso(
    estado: EstadoDeConexion, *, destinatarios: tuple[str, ...] = ("ana@empresa.com",)
) -> AvisoDeIntegracion:
    return AvisoDeIntegracion(
        destinatarios=destinatarios,
        sistema=SistemaExterno.WHATSAPP,
        estado=estado,
        detalle="Meta rechazo el nombre para mostrar",
    )


def _texto(correo: EmailMessage) -> str:
    return "".join(str(parte.get_content()) for parte in correo.walk() if not parte.is_multipart())


async def test_una_integracion_conectada_avisa_con_el_asunto_correcto() -> None:
    transporte = TransporteEspia()

    await AvisoPorEmail(transporte, URL_BASE).avisar(_aviso(EstadoDeConexion.CONECTADO))

    correo = transporte.enviados[0]
    assert "quedo conectado" in str(correo["Subject"])
    assert "WhatsApp Business" in str(correo["Subject"])
    assert correo["From"] == REMITENTE


async def test_una_integracion_rechazada_avisa_el_motivo() -> None:
    """Tercer criterio de aceptación: se notifica el motivo."""
    transporte = TransporteEspia()

    await AvisoPorEmail(transporte, URL_BASE).avisar(_aviso(EstadoDeConexion.NO_CONECTADO))

    correo = transporte.enviados[0]
    assert "No pudimos conectar" in str(correo["Subject"])
    assert "Meta rechazo el nombre para mostrar" in _texto(correo)


async def test_el_aviso_lleva_el_enlace_a_la_pantalla_de_integraciones() -> None:
    """PAN-CFG-INT — es donde el Administrador puede hacer algo al respecto."""
    transporte = TransporteEspia()

    await AvisoPorEmail(transporte, f"{URL_BASE}/").avisar(_aviso(EstadoDeConexion.CONECTADO))

    assert f"{URL_BASE}/configuracion/integraciones" in _texto(transporte.enviados[0])


async def test_atencion_se_cuenta_como_conectada_para_el_aviso() -> None:
    """Está funcionando y degradada: decir «no pudimos conectar» sería falso."""
    transporte = TransporteEspia()

    await AvisoPorEmail(transporte, URL_BASE).avisar(_aviso(EstadoDeConexion.ATENCION))

    assert "quedo conectado" in str(transporte.enviados[0]["Subject"])


async def test_sin_destinatarios_no_se_manda_nada_y_no_se_rompe() -> None:
    """Una empresa a medio onboardear puede no tener todavía una dirección confirmada.

    Perder el cambio de estado por eso sería peor que un aviso que nadie recibe.
    """
    transporte = TransporteEspia()

    await AvisoPorEmail(transporte, URL_BASE).avisar(
        _aviso(EstadoDeConexion.CONECTADO, destinatarios=())
    )

    assert transporte.enviados == []


async def test_un_servidor_de_correo_caido_no_deshace_el_cambio_de_estado() -> None:
    """A diferencia de la invitación, acá el fallo se traga: el cambio ya está auditado.

    Convertirlo en una excepción reintentaría el *sondeo*, y el sondeo es lo que escribió
    la fila de auditoría.
    """
    transporte = TransporteEspia(falla=True)

    await AvisoPorEmail(transporte, URL_BASE).avisar(_aviso(EstadoDeConexion.CONECTADO))


async def test_el_correo_lleva_texto_plano_y_html() -> None:
    transporte = TransporteEspia()

    await AvisoPorEmail(transporte, URL_BASE).avisar(_aviso(EstadoDeConexion.CONECTADO))

    tipos = {parte.get_content_type() for parte in transporte.enviados[0].walk()}
    assert "text/plain" in tipos
    assert "text/html" in tipos
