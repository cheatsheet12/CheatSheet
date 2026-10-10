"""El montaje de los avisos de turno por el canal real (U5 y U7), compartido por sus tests.

Meta es un `httpx.MockTransport`; los repositorios de `conversational` son en memoria. Los fixtures
`hilos` y `sin_plantillas_aprobadas` son autouse: cada módulo de test que los importa los hereda.
"""

from __future__ import annotations

from datetime import datetime

import httpx
from cheatsheet.api.agenda import armar_notificador
from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.contexts.conversational.application.ports import PortMensajeria
from cheatsheet.contexts.conversational.infrastructure.canal import (
    ConfiguracionDeMensajeria,
    MensajeriaWhatsApp,
)
from cheatsheet.contexts.scheduling.application.turnos import Avisador
from cheatsheet.contexts.scheduling.domain.turno import Turno
from cheatsheet.shared.roles import RolUsuario

from tests.contexts.conversational.application.dobles import (
    RepositorioConversacionEnMemoria,
    RepositorioMensajeEnMemoria,
)
from tests.contexts.scheduling.application.test_agenda import (
    AHORA as AHORA_DE_LA_AGENDA,
)
from tests.contexts.scheduling.application.test_agenda import (
    EMPRESA as EMPRESA_DE_LA_AGENDA,
)
from tests.contexts.scheduling.application.test_agenda import (
    USUARIO as USUARIO_DE_LA_AGENDA,
)
from tests.contexts.scheduling.application.test_agenda import Escena, un_recurso, un_turno


class SinPlantillas:
    """Sin plantilla aprobada: los adaptadores mandan su texto de fábrica (U5)."""

    async def para(self, codigo: str, variables: object) -> None:
        del codigo, variables
        return


class RelojFijo:
    def ahora(self) -> datetime:
        return AHORA_DE_LA_AGENDA


class EnMemoria:
    """Los repositorios de `conversational` que reciben los avisos de turno en estos tests (U7)."""

    def __init__(self) -> None:
        self.conversaciones = RepositorioConversacionEnMemoria()
        self.mensajes = RepositorioMensajeEnMemoria()


def unidad() -> UnidadDeTrabajo:
    return UnidadDeTrabajo(sesion=None, publicador=None, reloj=None)  # type: ignore[arg-type]


class Meta:
    """Un Meta falso: contesta lo que le toque (el último se repite) y cuenta los `POST`."""

    def __init__(self, *respuestas: httpx.Response) -> None:
        self._respuestas = list(respuestas)
        self.pedidos: list[httpx.Request] = []

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        self.pedidos.append(pedido)
        return self._respuestas[min(len(self.pedidos), len(self._respuestas)) - 1]


async def sin_esperar(segundos: float) -> None:
    del segundos


def canal_real(meta: Meta) -> MensajeriaWhatsApp:
    return MensajeriaWhatsApp(
        ConfiguracionDeMensajeria(
            token="fake-token-for-tests",
            phone_number_id="999",
            graph_url="https://graph.test",
            graph_version="v21.0",
            timeout_segundos=1.0,
        ),
        transporte=httpx.MockTransport(meta),
        esperar=sin_esperar,
    )


async def cancelar(escena: Escena, turno: Turno) -> Turno:
    return await escena.cancelar().ejecutar(
        empresa_id=EMPRESA_DE_LA_AGENDA,
        usuario_id=USUARIO_DE_LA_AGENDA,
        rol=RolUsuario.OPERADOR,
        turno_id=turno.id,
        ahora=AHORA_DE_LA_AGENDA,
    )


def escena_con_canal(canal: PortMensajeria) -> tuple[Escena, Turno]:
    recurso = un_recurso()
    turno = un_turno(recurso)
    escena = Escena(recurso, turno)
    escena.avisador = armar_avisador_con(escena, canal)
    return escena, turno


def armar_avisador_con(escena: Escena, canal: PortMensajeria) -> Avisador:
    """El avisador del panel, con los dobles de la escena y el notificador real de `api`."""
    return Avisador(
        clientes=escena.directorio,
        servicios=escena.catalogo,
        notificador=armar_notificador(unidad(), empresa_id=EMPRESA_DE_LA_AGENDA, canal=canal),
    )
