"""Errores de `reporting`.

Como en el resto del sistema, casi todos derivan de `EntradaInvalida` porque `api/main.py`
mapea ése a **422 reenviando el texto** — y en este contexto tres de esos textos los escriben
las historias palabra por palabra.

`AccesoNoDisponible` es la única que se contesta a alguien **sin sesión**, y por eso su texto
importa el doble: es todo lo que un contador va a ver cuando el enlace deje de funcionar.
"""

from __future__ import annotations

from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada


class ReporteInexistente(EntradaInvalida):
    """No es de esta empresa, o nunca existió. Bajo RLS son la misma respuesta, a propósito."""


class PaqueteInexistente(EntradaInvalida):
    """Ídem."""


class SinDatosEnElPeriodo(EntradaInvalida):
    """HU-E10-03, segundo criterio: «No hay datos para generar el reporte...».

    Se levanta **antes** de crear la fila del reporte: un `Reporte` que nace fallido porque no
    había nada que exportar es ruido en el historial de HU-E10-03.
    """


class ReporteNoDescargable(InvarianteViolada):
    """Todavía no está listo, o está listo y no tiene archivo.

    La segunda mitad no debería pasar —`completar` exige la referencia— y se comprueba igual:
    ofrecer una descarga que va a fallar es peor que decir que no está.
    """


class AccesoNoDisponible(EntradaInvalida):
    """HU-E10-06, tercer criterio. El enlace venció o el administrador lo revocó.

    **Las dos causas dan el mismo mensaje**, y es deliberado: distinguirlas le diría a alguien
    que probó un enlace ajeno si ese enlace existió alguna vez.
    """


class ContadorYaInvitado(InvarianteViolada):
    """HU-E10-05 RN-04: un solo contador externo activo por empresa.

    Para invitar a otro hay que revocar el anterior, que es lo que hace que «quién tiene acceso»
    tenga una respuesta y no una lista.
    """


class InvitacionNoEnviada(EntradaInvalida):
    """El correo con el enlace no salió, así que la invitación no ocurrió.

    Al revés que el aviso de un turno (D33) o el del agente (D48), donde el hecho de negocio ya
    había pasado y el canal era una consecuencia: acá **el enlace es el correo**. Levantar
    deshace la transacción y con ella el token, que es lo correcto — un token guardado que
    nadie recibió haría chocar la próxima invitación contra «ya hay un contador con acceso».
    """


class GeneracionFallida(EntradaInvalida):
    """El archivo no se pudo armar o guardar.

    El reporte queda en `FALLIDO` y **la fila se conserva**: es la evidencia de que hubo un
    problema, que es justo lo que alguien va a buscar cuando pregunte por qué su contador no
    recibió nada.
    """


__all__ = [
    "AccesoNoDisponible",
    "ContadorYaInvitado",
    "GeneracionFallida",
    "InvitacionNoEnviada",
    "PaqueteInexistente",
    "ReporteInexistente",
    "ReporteNoDescargable",
    "SinDatosEnElPeriodo",
]
