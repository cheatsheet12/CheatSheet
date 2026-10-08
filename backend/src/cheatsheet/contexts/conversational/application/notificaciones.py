"""`NotificarAlCliente` — el aviso de un turno, guardado como mensaje del sistema (U7, D-U7-4).

`scheduling` avisa al cliente cuando el panel cancela, reprograma o confirma un turno. Hasta U7
ese aviso salía y no dejaba rastro; ahora queda en la **conversación del cliente** como un
`Mensaje` `SALIENTE`/`SISTEMA`, con su `wamid` y su estado de entrega (los callbacks `statuses[]`
lo encuentran por ese id, igual que a los del agente). Así el operador ve qué se le dijo, y cuando
el cliente contesta («sí, voy») el agente retoma el mismo hilo (HU-E8-04 RN-03).

**Orden: primero se manda, después se guarda.** El mensaje que se guarda lleva el `wamid` y el
estado real del envío, y para eso hay que saber cómo terminó.

**Nunca levanta por el canal.** Ningún fallo de WhatsApp puede deshacer un turno ya cancelado
(D33): el mensaje queda `FALLIDO` con el motivo (`motivo_de_falla_de`: el código de Meta o una
clase corta, nunca el texto del error) y el resultado lo informa. La falla **no se reintenta**
(D6): un aviso de cancelación tres horas tarde puede llegar después de la hora del turno, y el
operador la ve en el hilo para llamar al cliente.

**Sin canal conectado no se guarda nada** (`SIN_CANAL`): la empresa no usa WhatsApp y llenarle la
bandeja de hilos con avisos fallidos sería ruido.

**La escritura va en un savepoint propio** (`aislar`, `sesion.begin_nested` en la raíz): si la base
la rechaza, el savepoint se deshace, el turno sigue cancelado, el envío a Meta (que ya ocurrió) no
se repite y el resultado lleva `sin_registrar=True` para que el llamador lo deje en el log.

Ningún log de este módulo lleva el teléfono, el nombre ni el texto (`CLAUDE.md` §5): ni siquiera
hay logs; el resultado le informa al llamador lo que pasó.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from cheatsheet.contexts.conversational.application.errors import (
    CanalNoConectado,
    motivo_de_falla_de,
)
from cheatsheet.contexts.conversational.application.ports import (
    PortMensajeria,
    PortRepositorioConversacion,
    PortRepositorioMensaje,
)
from cheatsheet.contexts.conversational.domain.conversacion import (
    Conversacion,
    DireccionMensaje,
    EstadoEntrega,
    Mensaje,
    OrigenDelMensaje,
    TipoContenido,
)
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.externo_id import externo_id_o_ninguno


@dataclass(frozen=True, slots=True)
class PlantillaDeAviso:
    """Una plantilla **aprobada** lista para mandar: cómo se llama en Meta, idioma y parámetros."""

    nombre: str
    idioma: str
    parametros: Mapping[str, str] = field(repr=False)


@dataclass(frozen=True, slots=True)
class EnvioDeAviso:
    """Lo que hay que mandar y lo que se guarda: `texto` es siempre lo que el cliente lee.

    Con `plantilla` sale como plantilla (fuera de las 24 h Meta no acepta otra cosa) y `texto` es su
    cuerpo resuelto; sin ella sale como texto de fábrica. El texto lleva el nombre del cliente: no
    entra en el `repr`.
    """

    texto: str = field(repr=False)
    plantilla: PlantillaDeAviso | None = None


@dataclass(frozen=True, slots=True)
class ResultadoDeNotificacion:
    """Cómo terminó el aviso. `falla` es el motivo (`131047`, `INCIERTO`, `SIN_CANAL`…) o `None`.

    `sin_registrar` es verdadero cuando el envío se intentó y el mensaje **no se pudo guardar**: el
    llamador lo registra. Nunca es verdadero por `SIN_CANAL`, que no guarda nada a propósito.
    """

    enviado: bool
    externo_id: str | None = None
    falla: str | None = None
    sin_registrar: bool = False


class NotificarAlCliente:
    """Manda el aviso, lo guarda en la conversación del cliente y cuenta cómo salió."""

    def __init__(
        self,
        *,
        conversaciones: PortRepositorioConversacion,
        mensajes: PortRepositorioMensaje,
        mensajeria: PortMensajeria,
        aislar: Callable[[], AbstractAsyncContextManager[object]],
    ) -> None:
        self._conversaciones = conversaciones
        self._mensajes = mensajes
        self._mensajeria = mensajeria
        #: Abre un savepoint. El composition root le pasa `sesion.begin_nested`.
        self._aislar = aislar

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        cliente_id: UUID,
        telefono: str,
        envio: EnvioDeAviso,
        ahora: datetime,
    ) -> ResultadoDeNotificacion:
        externo_id: str | None = None
        motivo: str | None = None
        try:
            externo_id = externo_id_o_ninguno(await self._mandar(telefono, envio))
        except CanalNoConectado as sin_canal:
            return ResultadoDeNotificacion(enviado=False, falla=motivo_de_falla_de(sin_canal))
        except Exception as fallo:  # noqa: BLE001 — ver el docstring del módulo
            # Acotado por el motivo: **ningún fallo del canal puede deshacer el turno** (D33). El
            # puerto lo implementan adaptadores que levantan lo que su SDK levante; enumerarlos
            # acoplaría este caso de uso a su infraestructura. Sólo el motivo corto, nunca el texto.
            motivo = motivo_de_falla_de(fallo)
        estado = EstadoEntrega.ENVIADO if motivo is None else EstadoEntrega.FALLIDO
        guardado = await self._guardar(
            empresa_id, cliente_id, envio, estado, externo_id, motivo, ahora
        )
        return ResultadoDeNotificacion(
            enviado=motivo is None,
            externo_id=externo_id,
            falla=motivo,
            sin_registrar=not guardado,
        )

    async def _mandar(self, telefono: str, envio: EnvioDeAviso) -> str:
        plantilla = envio.plantilla
        if plantilla is None:
            return await self._mensajeria.enviar(telefono=telefono, texto=envio.texto)
        return await self._mensajeria.enviar_plantilla(
            telefono=telefono,
            nombre=plantilla.nombre,
            idioma=plantilla.idioma,
            parametros=plantilla.parametros,
        )

    async def _guardar(
        self,
        empresa_id: EmpresaId,
        cliente_id: UUID,
        envio: EnvioDeAviso,
        estado: EstadoEntrega,
        externo_id: str | None,
        motivo: str | None,
        ahora: datetime,
    ) -> bool:
        """Guarda el aviso en su hilo, en un savepoint. Devuelve si quedó guardado."""
        try:
            async with self._aislar():
                hilo = await self._hilo_de(empresa_id, cliente_id, ahora)
                await self._mensajes.agregar(
                    Mensaje(
                        id=uuid4(),
                        conversacion_id=hilo.id,
                        empresa_id=empresa_id,
                        direccion=DireccionMensaje.SALIENTE,
                        tipo_contenido=TipoContenido.TEXTO,
                        contenido=envio.texto,
                        momento=ahora,
                        origen=OrigenDelMensaje.SISTEMA,
                        estado_entrega=estado,
                        externo_id=externo_id,
                        motivo_de_falla=motivo,
                    )
                )
        except Exception:  # noqa: BLE001 — ver el docstring del módulo
            # El savepoint ya se deshizo al salir del bloque. Acotado por el motivo: el envío a
            # Meta ocurrió, el turno sigue como está y el llamador deja constancia
            # (`sin_registrar`). Aquí no se loguea nada: el texto de la excepción puede traer datos.
            return False
        return True

    async def _hilo_de(
        self, empresa_id: EmpresaId, cliente_id: UUID, ahora: datetime
    ) -> Conversacion:
        """El hilo activo del cliente o uno nuevo: el mismo camino que usa el agente (T10)."""
        abierta = await self._conversaciones.abierta_de(cliente_id, bloquear=True)
        if abierta is not None:
            abierta.registrar_actividad(ahora)
            await self._conversaciones.guardar(abierta)
            return abierta
        nueva = Conversacion(
            id=uuid4(), empresa_id=empresa_id, cliente_id=cliente_id, created_at=ahora
        )
        nueva.registrar_actividad(ahora)
        await self._conversaciones.agregar(nueva)
        return nueva


__all__ = [
    "EnvioDeAviso",
    "NotificarAlCliente",
    "PlantillaDeAviso",
    "ResultadoDeNotificacion",
]
