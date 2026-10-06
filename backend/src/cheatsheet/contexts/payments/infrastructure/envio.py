"""Por donde sale un recordatorio de cobro (HS-T3 RN-02): WhatsApp, como texto (U5, ADR-0011).

`EnvioPorWhatsApp` arma el texto de fabrica de `recordatorio_de_cobro` y lo manda por el canal
que el composition root le pasa. **No importa a `conversational`** (R3): el canal es un
`Protocol` local, `CanalDeTexto`, que el cliente de la Cloud API satisface por estructura.

**Nunca levanta.** Un fallo del canal es un recordatorio `FALLIDO`, no una excepcion: el barrido
sigue con el cobro siguiente y el paso queda registrado, asi el indice `(cobro_id, paso)` no lo
deja salir de nuevo. El `except` es amplio porque el adaptador no puede importar las excepciones
de `conversational`; el codigo de Meta ya quedo en el log del canal.

**Fuera de la ventana de 24 h Meta solo acepta plantillas** (error 131047): hasta la unidad
`plantillas-de-whatsapp-en-meta`, un recordatorio asi queda `FALLIDO`, visible en PAN-COB-02 y
nunca silencioso.

Ningun log lleva el nombre, el telefono ni el texto: son datos personales (`CLAUDE.md` §5).
"""

from __future__ import annotations

from typing import Protocol

from cheatsheet.contexts.payments.application.ports_envio import PortContactoDeCliente
from cheatsheet.contexts.payments.domain.cobro import Cobro
from cheatsheet.contexts.payments.domain.dinero import redondear
from cheatsheet.contexts.payments.domain.recordatorio import EstadoEntrega
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.empresa import EmpresaId

logger = obtener_logger(__name__)

#: El unico canal que este adaptador sabe usar. Los pasos `EMAIL` y `PANEL` de la cadena
#: (`business_config/domain/regla.py`) quedan `FALLIDO` hasta que tengan su propia unidad.
CANAL_WHATSAPP = "WHATSAPP"


class CanalDeTexto(Protocol):
    """Lo unico que `payments` necesita del canal: mandar un texto y recibir el id del mensaje."""

    async def enviar(self, *, telefono: str, texto: str) -> str: ...


def texto_de_recordatorio(*, nombre: str, cobro: Cobro) -> str:
    """El texto de fabrica de `recordatorio_de_cobro`.

    El monto sale con dos decimales y `ROUND_HALF_UP` (`Decimal`, nunca `float`). La linea del
    link va solo si el cobro tiene uno activo: un cobro por transferencia no tiene, y mandar
    «Podes pagarlo aca: None» seria peor que no decirlo.
    """
    texto = (
        f"Hola {nombre}, te recordamos el pago de {cobro.descripcion} "
        f"por $ {redondear(cobro.monto):.2f}."
    )
    if cobro.tiene_link_activo and cobro.link is not None:
        texto += f" Podés pagarlo acá: {cobro.link.url}"
    return texto


class EnvioPorWhatsApp:
    """`PortEnvioDeRecordatorio` sobre el canal de WhatsApp de la empresa."""

    def __init__(self, canal: CanalDeTexto, contactos: PortContactoDeCliente) -> None:
        self._canal = canal
        self._contactos = contactos

    async def enviar(
        self, *, empresa_id: EmpresaId, cobro: Cobro, canal: str, paso: int
    ) -> EstadoEntrega:
        del empresa_id
        if canal != CANAL_WHATSAPP:
            logger.warning(
                "recordatorio_canal_sin_adaptador", cobro_id=str(cobro.id), paso=paso, canal=canal
            )
            return EstadoEntrega.FALLIDO
        try:
            return await self._mandar(cobro, paso)
        except Exception as exc:  # noqa: BLE001 — ver el docstring del modulo
            # Acotado por el motivo: este adaptador no puede importar las excepciones de
            # `conversational` (R3), y **nada puede voltear el barrido**. Solo la clase de la
            # excepcion, nunca su texto: puede traer el numero.
            logger.warning(
                "recordatorio_fallido",
                cobro_id=str(cobro.id),
                paso=paso,
                causa=type(exc).__name__,
            )
            return EstadoEntrega.FALLIDO

    async def _mandar(self, cobro: Cobro, paso: int) -> EstadoEntrega:
        contacto = await self._contactos.contacto_de(cobro.cliente_id)
        if contacto is None:
            logger.info("recordatorio_sin_telefono", cobro_id=str(cobro.id), paso=paso)
            return EstadoEntrega.FALLIDO
        await self._canal.enviar(
            telefono=contacto.telefono,
            texto=texto_de_recordatorio(nombre=contacto.nombre, cobro=cobro),
        )
        return EstadoEntrega.ENVIADO


__all__ = ["CANAL_WHATSAPP", "CanalDeTexto", "EnvioPorWhatsApp", "texto_de_recordatorio"]
