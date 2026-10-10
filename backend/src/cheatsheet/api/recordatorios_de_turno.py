"""Donde se arma el barrido de recordatorios de turno (U8, D-U8-6, D-U8-12, D-U8-13).

Es la raíz de composición que ve a todos los contextos a la vez: `scheduling` (turnos, filas del
recordatorio), `master_data` (contacto y servicio, por el ACL de `scheduling`), `business_config` (la
agenda y la plantilla aprobada) y `conversational` (el canal y el mensaje `SISTEMA`). Se construye
**por unidad de trabajo**: todo está atado a la transacción y a la empresa.

**La identidad en el worker (D-U8-12).** El barrido no tiene un usuario que lo pidió, y el ACL de
servicios exige un rol: actúa con la identidad de sistema fija `OPERADOR`, la misma que el agente de
WhatsApp (`api/conversacional.py`). No se eleva a Administrador ni se saltea el control de lectura.

**Empresa sin WhatsApp (D-U8-13).** `armar_mensajeria` devuelve `SinCanal` cuando la empresa no
conectó WhatsApp en producción, y ese canal recién falla al enviar. Sin esta pregunta antes, el barrido
crearía una fila y un hilo `FALLIDO` por cada turno de cada empresa que no usa WhatsApp.
`sin_canal_conectado` es esa pregunta, y la hace la tarea en la raíz del barrido.
"""

from __future__ import annotations

from cheatsheet.api.agenda import armar_catalogo, armar_directorio
from cheatsheet.api.avisos_de_turno import armar_canal_de_avisos
from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.api.plantillas_salientes import armar_plantillas_aprobadas
from cheatsheet.contexts.business_config.application.agenda import ConsultarAgendaDeNotificacion
from cheatsheet.contexts.business_config.infrastructure.ensamblado import ConfiguracionDeNegocio
from cheatsheet.contexts.conversational.application.ports import PortMensajeria
from cheatsheet.contexts.conversational.infrastructure.canal import SinCanal
from cheatsheet.contexts.scheduling.application.envio_de_recordatorios import EnvioDeRecordatorios
from cheatsheet.contexts.scheduling.application.recordatorios import EnviarRecordatoriosDeTurno
from cheatsheet.contexts.scheduling.infrastructure.agenda_de_notificacion import (
    AgendaViaConfiguracion,
)
from cheatsheet.contexts.scheduling.infrastructure.recordatorio_por_whatsapp import (
    RecordatorioPorWhatsApp,
)
from cheatsheet.contexts.scheduling.infrastructure.repositories import RepositorioTurnoPostgres
from cheatsheet.contexts.scheduling.infrastructure.repositorio_de_recordatorios import (
    RepositorioRecordatoriosDeTurnoPostgres,
)
from cheatsheet.platform.transaccion import AislamientoConSavepoint, ConfirmacionDeLaUnidad
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.roles import RolUsuario

#: La identidad con la que el barrido lee el catálogo de servicios: la misma del agente.
ROL_DEL_BARRIDO = RolUsuario.OPERADOR


def sin_canal_conectado(canal: PortMensajeria) -> bool:
    """La empresa no conectó WhatsApp (producción): no hay a quién mandarle ni hilo que llenar."""
    return isinstance(canal, SinCanal)


def armar_recordatorios_de_turno(
    unidad: UnidadDeTrabajo, *, empresa_id: EmpresaId, canal: PortMensajeria
) -> EnviarRecordatoriosDeTurno:
    """El barrido de esta empresa, sobre la transacción de esta unidad de trabajo."""
    turnos = RepositorioTurnoPostgres(unidad.sesion)
    recordatorios = RepositorioRecordatoriosDeTurnoPostgres(unidad.sesion)
    return EnviarRecordatoriosDeTurno(
        turnos=turnos,
        recordatorios=recordatorios,
        agenda=AgendaViaConfiguracion(
            ConsultarAgendaDeNotificacion(ConfiguracionDeNegocio.armar(unidad).reglas),
            empresa_id=empresa_id,
        ),
        envio=EnvioDeRecordatorios(
            turnos=turnos,
            recordatorios=recordatorios,
            envio=RecordatorioPorWhatsApp(
                clientes=armar_directorio(unidad, empresa_id=empresa_id),
                servicios=armar_catalogo(unidad, empresa_id=empresa_id, rol=ROL_DEL_BARRIDO),
                canal=armar_canal_de_avisos(unidad, empresa_id=empresa_id, canal=canal),
                plantillas=armar_plantillas_aprobadas(unidad),
            ),
            publicador=unidad.publicador,
            aislamiento=AislamientoConSavepoint(unidad.sesion),
            # Confirma cada recordatorio antes y después de hablar con Meta (D-U8-10).
            transaccion=ConfirmacionDeLaUnidad(unidad.sesion, empresa_id),
            # El reloj real: ventanas y fechas se miden al escribir (S2 de U7).
            reloj=unidad.reloj,
        ),
    )


__all__ = ["ROL_DEL_BARRIDO", "armar_recordatorios_de_turno", "sin_canal_conectado"]
