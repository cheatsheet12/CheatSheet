"""Por donde sale un recordatorio de cobro (HS-T3 RN-02): WhatsApp, como texto (U5, ADR-0011).

`EnvioPorWhatsApp` manda el recordatorio por el canal que el composition root le pasa. **No
importa a `conversational` ni a `business_config`** (R3): el canal y las plantillas son `Protocol`s
locales (`CanalDeTexto`, `PlantillasAprobadas`) que el cliente de la Cloud API y el caso de uso de
`business_config` satisfacen por estructura.

**Plantilla aprobada si la hay (U6).** Fuera de la ventana de 24 h Meta solo acepta plantillas, y
dentro de ella una plantilla de utilidad cuesta lo mismo que un texto: por eso, si la empresa tiene
aprobada la de `recordatorio_de_cobro`, el recordatorio sale **siempre** como plantilla. Si no,
sale el texto de fabrica de este modulo, **nunca el cuerpo editado de una plantilla no aprobada**
(RN-04).

**Nunca levanta.** Un fallo del canal es un recordatorio `FALLIDO`, no una excepcion: el barrido
sigue con el cobro siguiente y el paso queda registrado, asi el indice `(cobro_id, paso)` no lo
deja salir de nuevo. El `except` es amplio porque el adaptador no puede importar las excepciones
de `conversational`; el codigo de Meta ya quedo en el log del canal.

Sin plantilla aprobada, fuera de la ventana Meta contesta 131047: el recordatorio queda
`FALLIDO`, visible en PAN-COB-02 y nunca silencioso (el codigo queda en el log del canal).

Ningun log lleva el nombre, el telefono ni el texto: son datos personales (`CLAUDE.md` §5).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from cheatsheet.contexts.payments.application.ports_de_recordatorios import ResultadoDeEnvio
from cheatsheet.contexts.payments.application.ports_envio import (
    FallaDelCanal,
    PortContactoDeCliente,
)
from cheatsheet.contexts.payments.domain.cobro import Cobro
from cheatsheet.contexts.payments.domain.dinero import formatear_es_ar, redondear
from cheatsheet.contexts.payments.domain.recordatorio import EstadoEntrega
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.zona_horaria import ZONA_ARGENTINA

logger = obtener_logger(__name__)

#: El unico canal que este adaptador sabe usar. Los pasos `EMAIL` y `PANEL` de la cadena
#: (`business_config/domain/regla.py`) quedan `FALLIDO` hasta que tengan su propia unidad.
CANAL_WHATSAPP = "WHATSAPP"

#: El codigo de la plantilla en `business_config` (HU-E11-02).
CODIGO_RECORDATORIO = "recordatorio_de_cobro"

#: Un parametro de plantilla no puede ir vacio: un cobro por transferencia no tiene link.
SIN_LINK = "— (pagás por transferencia)"


class CanalDeTexto(Protocol):
    """Lo unico que `payments` necesita del canal: mandar un texto o una plantilla aprobada."""

    async def enviar(self, *, telefono: str, texto: str) -> str: ...

    async def enviar_plantilla(
        self, *, telefono: str, nombre: str, idioma: str, parametros: Mapping[str, str]
    ) -> str: ...


class PlantillaParaMandar(Protocol):
    """Lo que `payments` lee de una plantilla aprobada: como se llama en Meta y sus parametros."""

    @property
    def nombre_en_meta(self) -> str: ...

    @property
    def idioma(self) -> str: ...

    @property
    def parametros(self) -> Mapping[str, str]: ...


class PlantillasAprobadas(Protocol):
    """La plantilla **aprobada** de un codigo, o `None` (no existe, no esta aprobada, otro canal).

    La raiz de composicion la respalda con `ConsultarPlantillaParaEnviar` de `business_config`.
    `None` significa «manda tu texto de fabrica».
    """

    async def para(
        self, codigo: str, variables: Mapping[str, str]
    ) -> PlantillaParaMandar | None: ...


def variables_de_recordatorio(*, nombre: str, cobro: Cobro) -> dict[str, str]:
    """Las variables de `recordatorio_de_cobro`, todas `str`.

    El monto va con `Decimal` y `ROUND_HALF_UP` en formato argentino (`12.500,00`); el vencimiento,
    en la fecha de Argentina; y el link, o `SIN_LINK` si el cobro no tiene uno activo.
    """
    link = cobro.link.url if cobro.tiene_link_activo and cobro.link is not None else SIN_LINK
    return {
        "nombre": nombre,
        "concepto": cobro.descripcion,
        "monto": formatear_es_ar(cobro.monto),
        "link": link,
        "vencimiento": cobro.vence_el.astimezone(ZONA_ARGENTINA).strftime("%d/%m/%Y"),
    }


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

    def __init__(
        self,
        canal: CanalDeTexto,
        contactos: PortContactoDeCliente,
        plantillas: PlantillasAprobadas,
    ) -> None:
        self._canal = canal
        self._contactos = contactos
        self._plantillas = plantillas

    async def enviar(
        self, *, empresa_id: EmpresaId, cobro: Cobro, canal: str, paso: int
    ) -> ResultadoDeEnvio:
        del empresa_id
        if canal != CANAL_WHATSAPP:
            logger.warning(
                "recordatorio_canal_sin_adaptador", cobro_id=str(cobro.id), paso=paso, canal=canal
            )
            return ResultadoDeEnvio(estado=EstadoEntrega.FALLIDO, codigo="CANAL_NO_SOPORTADO")
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
            # `FallaDelCanal` trae el motivo que la raiz tradujo; cualquier otra cosa es `ERROR`.
            if isinstance(exc, FallaDelCanal):
                return ResultadoDeEnvio(
                    estado=EstadoEntrega.FALLIDO, codigo=exc.codigo, transitoria=exc.transitoria
                )
            return ResultadoDeEnvio(estado=EstadoEntrega.FALLIDO, codigo="ERROR")

    async def _mandar(self, cobro: Cobro, paso: int) -> ResultadoDeEnvio:
        contacto = await self._contactos.contacto_de(cobro.cliente_id)
        if contacto is None:
            logger.info("recordatorio_sin_telefono", cobro_id=str(cobro.id), paso=paso)
            return ResultadoDeEnvio(estado=EstadoEntrega.FALLIDO, codigo="SIN_TELEFONO")
        plantilla = await self._plantillas.para(
            CODIGO_RECORDATORIO, variables_de_recordatorio(nombre=contacto.nombre, cobro=cobro)
        )
        if plantilla is not None:
            externo_id = await self._canal.enviar_plantilla(
                telefono=contacto.telefono,
                nombre=plantilla.nombre_en_meta,
                idioma=plantilla.idioma,
                parametros=plantilla.parametros,
            )
        else:
            externo_id = await self._canal.enviar(
                telefono=contacto.telefono,
                texto=texto_de_recordatorio(nombre=contacto.nombre, cobro=cobro),
            )
        return ResultadoDeEnvio(estado=EstadoEntrega.ENVIADO, externo_id=externo_id)


__all__ = [
    "CANAL_WHATSAPP",
    "CODIGO_RECORDATORIO",
    "SIN_LINK",
    "CanalDeTexto",
    "EnvioPorWhatsApp",
    "PlantillaParaMandar",
    "PlantillasAprobadas",
    "texto_de_recordatorio",
    "variables_de_recordatorio",
]
