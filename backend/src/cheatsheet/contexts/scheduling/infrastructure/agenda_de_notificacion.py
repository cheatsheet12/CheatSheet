"""ACL sobre `business_config`: la agenda de recordatorios, en el vocabulario de `scheduling`.

La misma forma que `payments/infrastructure/cadena.py`: el contexto que publica ofrece un contrato
(`ConsultarAgendaDeNotificacion`) y no conoce a sus consumidores; cada consumidor lo traduce.

**Lo que esta capa decide.** `business_config` responde con un default y un `configurada`; para el
barrido esa distinción no cambia nada —lo que necesita son las anticipaciones— así que se aplana. Una
agenda **vacía** es la decisión explícita del negocio de no avisar. Y una regla **malformada** se
traduce a `AgendaDeNotificacionInvalida`, con el `regla_id` para el log, para que el barrido saltee esa
empresa sin conocer los errores del otro contexto.
"""

from __future__ import annotations

from cheatsheet.contexts.business_config.application.agenda import ConsultarAgendaDeNotificacion
from cheatsheet.contexts.business_config.application.errors import AgendaMalFormada
from cheatsheet.contexts.scheduling.application.errors import AgendaDeNotificacionInvalida
from cheatsheet.shared.empresa import EmpresaId


class AgendaViaConfiguracion:
    """`PortAgendaDeNotificacion`, respaldado por el servicio de aplicación del otro contexto."""

    def __init__(self, consulta: ConsultarAgendaDeNotificacion, *, empresa_id: EmpresaId) -> None:
        self._consulta = consulta
        self._empresa_id = empresa_id

    async def anticipaciones(self) -> tuple[int, ...]:
        try:
            vigente = await self._consulta.ejecutar(empresa_id=self._empresa_id)
        except AgendaMalFormada as mala:
            raise AgendaDeNotificacionInvalida(str(mala), regla_id=mala.regla_id) from mala
        return vigente.anticipaciones_min


__all__ = ["AgendaViaConfiguracion"]
