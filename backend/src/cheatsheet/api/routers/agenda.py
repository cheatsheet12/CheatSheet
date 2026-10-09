"""Superficie HTTP de la agenda (HU-E7-01 … HU-E7-06).

`EmpresaMiddleware` ya puso la empresa, el usuario y el rol en `request.state`. El rol se pasa
al caso de uso en vez de comprobarlo acá, por lo que dicen los demás routers y probó PRU-09.

**No hay `DELETE` en ninguna de las dos entidades.** Un turno se cancela —queda en la agenda,
con su estado, que es lo que hace auditable la ocupación de un recurso— y un recurso se
desactiva (HU-E7-04 RN-03). Borrar cualquiera de los dos dejaría la agenda histórica apuntando
a algo que ya no existe.

**El rango por defecto es el día en curso** (HU-E7-01 RN-01), y se calcula acá y no en el caso
de uso: «hoy» depende de la zona horaria de la agenda, que es presentación, mientras que
`VerAgenda` contesta por cualquier rango — que es lo que van a necesitar el agente del épico 8
y el reporte del épico 9.
"""

from __future__ import annotations

from cheatsheet.api.dependencies import Recursos
from cheatsheet.api.routers.agenda_recursos import rutas_de_recursos
from cheatsheet.api.routers.agenda_turnos import rutas_de_turnos
from fastapi import APIRouter


def crear_router(recursos: Recursos) -> APIRouter:
    router = APIRouter(tags=["scheduling"])
    router.include_router(rutas_de_recursos(recursos), prefix="/recursos")
    router.include_router(rutas_de_turnos(recursos), prefix="/turnos")
    return router
