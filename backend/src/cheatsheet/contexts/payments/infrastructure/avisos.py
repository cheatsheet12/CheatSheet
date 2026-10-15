"""Por dónde sale el aviso de un cobro confirmado (HU-E8-04 RN-01): WhatsApp (ADR-0011).

`AvisoDePagoPorWhatsApp` manda el aviso por el canal que la raíz de composición le pasa. **No importa
a `conversational` ni a `business_config`** (R3): el canal y las plantillas son `Protocol`s locales
(`CanalDeAvisos`, `PlantillasParaAvisos`) que la raíz respalda con `NotificarAlCliente` y con el caso
de uso de `business_config`. Es el mismo patrón que los avisos de turno
(`scheduling/infrastructure/avisos.py`).

**El aviso queda guardado.** `CanalDeAvisos.notificar` no solo manda: la raíz lo respalda con
`NotificarAlCliente`, que además registra el aviso como mensaje del sistema en la conversación del
cliente. Si el mensaje no se pudo guardar, el resultado lo dice y acá queda el log
`aviso_de_pago_sin_registrar`; el pago sigue como estaba. Los avisos fallidos **no se reintentan**
(D6 de U7): la falla queda visible en el hilo.

**Plantilla aprobada si la hay (U6).** Fuera de la ventana de 24 h Meta solo acepta plantillas, y
dentro de ella una plantilla de utilidad cuesta lo mismo que un texto: por eso, si la empresa tiene
aprobada la de `cobro_pagado`, el aviso sale **siempre** como plantilla. Si no, sale el texto de
fábrica de este módulo, **nunca el cuerpo editado de una plantilla no aprobada** (RN-04). Sin
plantilla aprobada, fuera de la ventana Meta contesta 131047: el aviso queda `FALLIDO` en el hilo.

**El monto** va con `Decimal` y `ROUND_HALF_UP` en formato argentino (`formatear_es_ar`), nunca por
`float`.

Ningún log lleva el nombre, el teléfono, el concepto ni el texto: son datos personales
(`CLAUDE.md` §5). Lo que se registra es el motivo (un código de Meta o una clase corta).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from cheatsheet.contexts.payments.application.ports_envio import DatosDeAvisoDePago
from cheatsheet.contexts.payments.domain.dinero import formatear_es_ar
from cheatsheet.platform.telemetry import obtener_logger

logger = obtener_logger(__name__)

#: El código de la plantilla en `business_config` (HU-E11-02).
CODIGO_COBRO_PAGADO = "cobro_pagado"


@dataclass(frozen=True, slots=True)
class PlantillaParaAviso:
    """Una plantilla aprobada lista para mandar. Los parámetros llevan el nombre: no van al `repr`."""

    nombre: str
    idioma: str
    parametros: Mapping[str, str] = field(repr=False)


@dataclass(frozen=True, slots=True)
class EnvioParaAviso:
    """Lo que el cliente va a leer (`texto`) y, si la hay, la plantilla aprobada por la que sale."""

    texto: str = field(repr=False)
    plantilla: PlantillaParaAviso | None = None


@dataclass(frozen=True, slots=True)
class ResultadoLocal:
    """Cómo terminó el aviso, en el vocabulario de `payments`.

    `falla` es el motivo si no salió (`131047`, `INCIERTO`, `SIN_CANAL`…); `sin_registrar` es que se
    intentó y el mensaje no quedó guardado en la conversación, y `causa` es entonces la clase de la
    excepción que lo impidió (nunca su texto).
    """

    enviado: bool
    falla: str | None = None
    sin_registrar: bool = False
    causa: str | None = None


class CanalDeAvisos(Protocol):
    """Lo único que `payments` necesita del canal: avisar a un cliente y que quede registrado.

    **Nunca levanta por el canal**: el motivo viaja en el resultado. La raíz de composición lo
    respalda con `NotificarAlCliente` de `conversational`.
    """

    async def notificar(
        self, *, cliente_id: UUID, telefono: str, envio: EnvioParaAviso
    ) -> ResultadoLocal: ...


class PlantillaParaAvisar(Protocol):
    """Lo que `payments` lee de una plantilla aprobada: cómo se llama en Meta, parámetros y cuerpo."""

    @property
    def nombre_en_meta(self) -> str: ...

    @property
    def idioma(self) -> str: ...

    @property
    def parametros(self) -> Mapping[str, str]: ...

    @property
    def texto(self) -> str:
        """El cuerpo resuelto: lo que el cliente lee, y lo que se guarda en la conversación."""
        ...


class PlantillasParaAvisos(Protocol):
    """La plantilla **aprobada** de un código, o `None` (no existe, no está aprobada, otro canal).

    La raíz de composición la respalda con `ConsultarPlantillaParaEnviar` de `business_config`.
    `None` significa «mandá tu texto de fábrica».
    """

    async def para(
        self, codigo: str, variables: Mapping[str, str]
    ) -> PlantillaParaAvisar | None: ...


def variables_de_aviso_de_pago(datos: DatosDeAvisoDePago) -> dict[str, str]:
    """Las variables de `cobro_pagado`, todas `str`. La fecha de pago queda afuera (D91)."""
    return {
        "nombre": datos.nombre,
        "concepto": datos.concepto,
        "monto": formatear_es_ar(datos.monto),
    }


def texto_de_aviso_de_pago(datos: DatosDeAvisoDePago) -> str:
    """El texto de fábrica de `cobro_pagado`.

    Dice lo mismo que `DE_FABRICA["cobro_pagado"]`, con el monto en el mismo formato argentino que
    el parámetro de la plantilla (`$ 1.234,50`).
    """
    return (
        f"Hola {datos.nombre}, recibimos tu pago de {datos.concepto} "
        f"por $ {formatear_es_ar(datos.monto)}. ¡Gracias!"
    )


class AvisoDePagoPorWhatsApp:
    """`PortAvisoDePago` sobre el canal de WhatsApp de la empresa."""

    def __init__(self, canal: CanalDeAvisos, plantillas: PlantillasParaAvisos) -> None:
        self._canal = canal
        self._plantillas = plantillas

    async def avisar(self, datos: DatosDeAvisoDePago) -> None:
        plantilla = await self._plantillas.para(
            CODIGO_COBRO_PAGADO, variables_de_aviso_de_pago(datos)
        )
        resultado = await self._canal.notificar(
            cliente_id=datos.cliente_id,
            telefono=datos.telefono,
            envio=_envio_de(plantilla, texto_de_aviso_de_pago(datos)),
        )
        if resultado.falla is not None:
            # El motivo es un código de Meta o una clase corta: nunca el texto del error.
            logger.warning(
                "aviso_de_pago_fallido", cobro_id=str(datos.cobro_id), causa=resultado.falla
            )
        if resultado.sin_registrar:
            logger.warning(
                "aviso_de_pago_sin_registrar", cobro_id=str(datos.cobro_id), causa=resultado.causa
            )


def _envio_de(plantilla: PlantillaParaAvisar | None, texto_de_fabrica: str) -> EnvioParaAviso:
    """Plantilla aprobada si la hay (con su cuerpo resuelto); si no, el texto de fábrica."""
    if plantilla is None:
        return EnvioParaAviso(texto=texto_de_fabrica)
    return EnvioParaAviso(
        texto=plantilla.texto,
        plantilla=PlantillaParaAviso(
            nombre=plantilla.nombre_en_meta,
            idioma=plantilla.idioma,
            parametros=plantilla.parametros,
        ),
    )


__all__ = [
    "CODIGO_COBRO_PAGADO",
    "AvisoDePagoPorWhatsApp",
    "CanalDeAvisos",
    "EnvioParaAviso",
    "PlantillaParaAvisar",
    "PlantillaParaAviso",
    "PlantillasParaAvisos",
    "ResultadoLocal",
    "texto_de_aviso_de_pago",
    "variables_de_aviso_de_pago",
]
