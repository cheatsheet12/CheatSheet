"""Por dónde sale el recordatorio de un turno: WhatsApp (U8, D-U8-9).

`RecordatorioPorWhatsApp` es el `PortEnvioDeRecordatorioDeTurno` en sus dos tiempos y **reusa** de
`avisos.py` el canal (`CanalDeAvisos`), las plantillas aprobadas (`PlantillasAprobadas`) y las
variables (`variables_de_aviso`): el recordatorio sale por el mismo camino que los avisos de turno y,
como ellos, **queda guardado como mensaje `SISTEMA`** en la conversación del cliente, con su `wamid` y
su estado de entrega (la raíz lo respalda con `NotificarAlCliente`).

- **`preparar`** lee contacto, servicio y plantilla (todo lectura, corre dentro de la reserva). Sin
  teléfono devuelve `SinTelefono`. Con la plantilla `recordatorio_de_turno` aprobada sale como
  plantilla; si no, sale el texto de fábrica de este módulo, **nunca el cuerpo editado de una
  plantilla no aprobada** (RN-04). Fuera de la ventana de 24 h de Meta, sin plantilla aprobada el
  recordatorio falla siempre con 131047 (D-U8-18).
- **`mandar`** solo habla con el canal y **nunca levanta**: la falla es un resultado.

No importa a `conversational` ni a `business_config` (R3). Ningún log lleva el nombre, el teléfono ni
el texto: solo la clase del aviso y la clase de la excepción.
"""

from __future__ import annotations

from cheatsheet.contexts.scheduling.application.ports import (
    DatosDeAviso,
    PortCatalogoDeServicios,
    PortDirectorioDeClientes,
)
from cheatsheet.contexts.scheduling.application.ports_de_recordatorios import (
    PlantillaDelRecordatorio,
    RecordatorioListo,
    ResultadoDelEnvio,
    SinTelefono,
)
from cheatsheet.contexts.scheduling.domain.turno import Turno
from cheatsheet.contexts.scheduling.infrastructure.avisos import (
    CanalDeAvisos,
    EnvioParaAviso,
    PlantillaParaAviso,
    PlantillasAprobadas,
    dia_local,
    hora_local,
    variables_de_aviso,
)
from cheatsheet.platform.telemetry import obtener_logger

logger = obtener_logger(__name__)

#: El código de plantilla de `business_config` (HU-E11-02) del recordatorio.
CODIGO_RECORDATORIO = "recordatorio_de_turno"


def texto_de_recordatorio(datos: DatosDeAviso) -> str:
    """El texto de fábrica: el respaldo cuando no hay plantilla aprobada."""
    return (
        f"Hola {datos.nombre_del_cliente}, te recordamos tu turno de {datos.servicio} "
        f"el {dia_local(datos.inicio)} a las {hora_local(datos.inicio)}."
    )


class RecordatorioPorWhatsApp:
    """`PortEnvioDeRecordatorioDeTurno` sobre el canal de WhatsApp de la empresa."""

    def __init__(
        self,
        *,
        clientes: PortDirectorioDeClientes,
        servicios: PortCatalogoDeServicios,
        canal: CanalDeAvisos,
        plantillas: PlantillasAprobadas,
    ) -> None:
        self._clientes = clientes
        self._servicios = servicios
        self._canal = canal
        self._plantillas = plantillas

    async def preparar(
        self, turno: Turno, anticipacion_min: int
    ) -> RecordatorioListo | SinTelefono:
        contacto = await self._clientes.contacto_de(turno.cliente_id)
        if contacto is None:
            return SinTelefono()
        nombre, telefono = contacto
        servicio = await self._servicios.buscar_agendable(turno.servicio_id)
        datos = DatosDeAviso(
            cliente_id=turno.cliente_id,
            telefono=telefono,
            nombre_del_cliente=nombre,
            # Un servicio que dejó de ser agendable después de reservado sigue teniendo turnos.
            servicio=servicio.nombre if servicio is not None else "el servicio",
            # El recordatorio no nombra el recurso (las variables de la plantilla son cuatro).
            recurso="",
            inicio=turno.franja.inicio,
        )
        plantilla = await self._plantillas.para(CODIGO_RECORDATORIO, variables_de_aviso(datos))
        if plantilla is None:
            return RecordatorioListo(
                turno_id=turno.id,
                cliente_id=turno.cliente_id,
                anticipacion_min=anticipacion_min,
                telefono=telefono,
                texto=texto_de_recordatorio(datos),
            )
        return RecordatorioListo(
            turno_id=turno.id,
            cliente_id=turno.cliente_id,
            anticipacion_min=anticipacion_min,
            telefono=telefono,
            texto=plantilla.texto,
            plantilla=PlantillaDelRecordatorio(
                nombre=plantilla.nombre_en_meta,
                idioma=plantilla.idioma,
                parametros=plantilla.parametros,
            ),
        )

    async def mandar(self, listo: RecordatorioListo) -> ResultadoDelEnvio:
        plantilla = listo.plantilla
        try:
            resultado = await self._canal.notificar(
                cliente_id=listo.cliente_id,
                telefono=listo.telefono,
                envio=EnvioParaAviso(
                    texto=listo.texto,
                    plantilla=(
                        PlantillaParaAviso(
                            nombre=plantilla.nombre,
                            idioma=plantilla.idioma,
                            parametros=plantilla.parametros,
                        )
                        if plantilla is not None
                        else None
                    ),
                ),
            )
        except Exception as exc:  # noqa: BLE001 — ver el docstring del módulo
            # Acotado por el motivo: este adaptador no puede importar las excepciones de
            # `conversational` (R3) y el contrato dice que `mandar` nunca levanta. Solo la clase.
            logger.warning("recordatorio_de_turno_fallido", causa=type(exc).__name__)
            return ResultadoDelEnvio(enviado=False, falla="ERROR")
        if resultado.sin_registrar:
            # Salió pero no quedó guardado en el hilo: no se reintenta (ya salió).
            logger.warning("recordatorio_de_turno_sin_registrar", causa=resultado.causa)
        return ResultadoDelEnvio(
            enviado=resultado.enviado, falla=resultado.falla, transitoria=resultado.transitoria
        )


__all__ = ["CODIGO_RECORDATORIO", "RecordatorioPorWhatsApp", "texto_de_recordatorio"]
