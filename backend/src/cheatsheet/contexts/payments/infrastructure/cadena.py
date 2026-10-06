"""ACL sobre `business_config`: la cadena de recordatorios, en el vocabulario de `payments`.

La forma que ADR-0003 pide y que este sistema ya usa tres veces sobre el padrón: el contexto
que publica ofrece un contrato y no conoce a ninguno de sus consumidores; cada consumidor lo
traduce a sus términos.

**Lo que esta capa decide es qué hacer sin regla configurada.** `business_config` responde con
su default y avisa que no está configurada; para `payments` esa distinción no cambia nada —lo
que necesita son los pasos— así que se aplana. Guardar el `configurada` acá sería arrastrar
una pregunta que este contexto no tiene por qué contestar.
"""

from __future__ import annotations

from cheatsheet.contexts.business_config.application.reglas import ConsultarReglasVigentes
from cheatsheet.contexts.payments.application.ports_de_recordatorios import PasoDeCadena
from cheatsheet.shared.empresa import EmpresaId


class CadenaViaConfiguracion:
    """`PortCadenaDeEscalamiento`, respaldado por el servicio de aplicacion del otro contexto."""

    def __init__(self, consulta: ConsultarReglasVigentes) -> None:
        self._consulta = consulta

    async def pasos(self, *, empresa_id: EmpresaId) -> tuple[PasoDeCadena, ...]:
        vigentes = await self._consulta.ejecutar(empresa_id=empresa_id)
        # Ya vienen ordenados por dia: la normalizacion es del dominio del otro contexto, y
        # reordenar aca seria una segunda implementacion de la misma regla.
        return tuple(
            PasoDeCadena(dias=paso.dias, canal=paso.canal.value)
            for paso in vigentes.escalamiento.pasos
        )


__all__ = ["CadenaViaConfiguracion"]
