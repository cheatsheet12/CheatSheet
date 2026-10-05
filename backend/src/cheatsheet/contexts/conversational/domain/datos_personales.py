"""Datos personales y el modelo de lenguaje (`CLAUDE.md` §3.6, T11 del plan de la unidad).

**Nunca se envían datos personales reales a un LLM sin ocultarlos antes.** El mensaje de un
cliente puede traer su teléfono, su DNI o un CBU; el historial puede traer lo que escribió un
operador sobre otra persona. Antes de llamar al intérprete, el texto y el historial pasan por
acá.

La regla de `ocultar_datos_personales` es conservadora donde importa y precisa donde no:

- oculta los **correos** y toda secuencia de **siete o más dígitos**, aunque lleve puntos, guiones
  o espacios (teléfono, DNI, CUIT/CUIL, CBU/CVU, tarjeta);
- deja pasar lo que el agente necesita entender: horas («10:30»), fechas («14/10») y el «2» de
  «el 2», que nunca llegan a siete dígitos seguidos.

Función pura, sin I/O ni framework (R1). La reutiliza `comprobante-por-whatsapp` (D97, paso 1).
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from cheatsheet.contexts.conversational.domain.conversacion import Mensaje, OrigenDelMensaje

DATO_OCULTO = "[dato oculto]"

#: Lo que el modelo ve en lugar de un mensaje que escribió una persona del negocio. El contenido de
#: un operador es texto libre sobre clientes reales y no le sirve al clasificador.
DESCRIPTOR_DEL_OPERADOR = "[Mensaje de un asesor]"

#: Ídem para los avisos automáticos del sistema (D-U7-5 de la unidad de estados de entrega).
DESCRIPTOR_DEL_SISTEMA = "[Aviso automático del negocio sobre un turno]"

#: Cuánto historial se le manda al intérprete: tres vueltas de conversación.
MENSAJES_DE_HISTORIAL = 6

_CORREO = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
#: Siete o más dígitos, con a lo sumo un espacio, punto o guion entre cada par. Un `+` delante
#: (`+54 9 11 …`) queda afuera a propósito: lo que se oculta son los números.
_DIGITOS = re.compile(r"(?<!\d)\d(?:[ .\-]?\d){6,}(?!\d)")


def ocultar_datos_personales(texto: str) -> str:
    """El texto con los correos y los números largos reemplazados por `[dato oculto]`."""
    return _DIGITOS.sub(DATO_OCULTO, _CORREO.sub(DATO_OCULTO, texto))


def historial_para_el_interprete(
    mensajes: Sequence[Mensaje], *, limite: int = MENSAJES_DE_HISTORIAL
) -> list[str]:
    """Lo que el intérprete ve del hilo: los entrantes y lo que dijo el agente, ocultados.

    Un mensaje del **operador** se reemplaza por su descriptor, y uno del **sistema** por el suyo:
    no son del cliente ni del agente, y su texto libre puede nombrar a cualquiera. **Es la única
    función que arma el historial**: así ninguna ruta puede olvidarse de ocultar.
    """
    return [_para_el_modelo(uno) for uno in mensajes[-limite:]]


def _para_el_modelo(mensaje: Mensaje) -> str:
    if mensaje.origen is OrigenDelMensaje.OPERADOR:
        return DESCRIPTOR_DEL_OPERADOR
    if mensaje.origen is OrigenDelMensaje.SISTEMA:
        return DESCRIPTOR_DEL_SISTEMA
    return ocultar_datos_personales(mensaje.contenido)


__all__ = [
    "DATO_OCULTO",
    "DESCRIPTOR_DEL_OPERADOR",
    "DESCRIPTOR_DEL_SISTEMA",
    "MENSAJES_DE_HISTORIAL",
    "historial_para_el_interprete",
    "ocultar_datos_personales",
]
