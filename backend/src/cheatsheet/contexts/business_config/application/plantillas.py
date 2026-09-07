"""Los casos de uso de las plantillas de notificación (HU-E11-02).

**Sólo el Administrador**, que es lo que dice la historia.

Dos cosas del archivo:

- **No hay alta ni baja.** Los códigos de plantilla los define el sistema —son los mensajes
  que el sistema manda— y una plantilla con un código que nadie envía es una plantilla que no
  se va a usar nunca. Lo que un administrador hace es **editar el cuerpo** de las que existen,
  que es exactamente el segundo criterio de la historia.

  Las filas se siembran por empresa la primera vez que se piden: `ListarPlantillas` completa
  las que faltan con el texto de fábrica. Sembrarlas en el alta de la empresa habría atado un
  épico a otro y habría dejado sin plantillas a las empresas creadas antes de este épico.

- **`ResolverPlantilla` devuelve `None` cuando no hay nada configurado**, y el llamador usa su
  texto por defecto. Un canal que se queda mudo porque falta una fila es peor que uno que
  manda el texto de fábrica.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from cheatsheet.contexts.business_config.application.ports import PortRepositorioPlantillas
from cheatsheet.contexts.business_config.domain.plantilla import (
    VARIABLES_POR_CODIGO,
    EstadoDeAprobacion,
    PlantillaDeNotificacion,
)
from cheatsheet.contexts.business_config.domain.regla import CanalNotificacion
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.roles import RolUsuario

MOTIVO_SOLO_ADMIN = "Solo un Administrador puede administrar las plantillas"

#: El texto de fábrica de cada código, y su canal.
#:
#: Son los mismos mensajes que los adaptadores de los épicos 6 y 7 tienen escritos adentro. Que
#: existan acá es lo que hace que se puedan editar; que sigan existiendo allá es lo que hace que
#: el sistema funcione mientras nadie los edite.
DE_FABRICA: dict[str, tuple[CanalNotificacion, str]] = {
    "turno_confirmado": (
        CanalNotificacion.WHATSAPP,
        "Hola {{nombre}}, te confirmamos tu turno de {{servicio}} con {{recurso}} el "
        "{{fecha}} a las {{hora}}.",
    ),
    "turno_cancelado": (
        CanalNotificacion.WHATSAPP,
        "Hola {{nombre}}, tu turno de {{servicio}} del {{fecha}} a las {{hora}} fue "
        "cancelado. Escribinos si querés reprogramarlo.",
    ),
    "turno_reprogramado": (
        CanalNotificacion.WHATSAPP,
        "Hola {{nombre}}, tu turno de {{servicio}} pasó al {{fecha}} a las {{hora}} "
        "(antes {{fecha_anterior}} a las {{hora_anterior}}).",
    ),
    "recordatorio_de_turno": (
        CanalNotificacion.WHATSAPP,
        "Hola {{nombre}}, te recordamos tu turno de {{servicio}} el {{fecha}} a las {{hora}}.",
    ),
    "recordatorio_de_cobro": (
        CanalNotificacion.WHATSAPP,
        "Hola {{nombre}}, te recordamos el pago de {{concepto}} por $ {{monto}}. "
        "Podés pagarlo acá: {{link}}",
    ),
    "cobro_generado": (
        CanalNotificacion.WHATSAPP,
        "Hola {{nombre}}, te dejamos el link para pagar {{concepto}} por $ {{monto}}: {{link}}",
    ),
}

#: El idioma de fábrica. El DER le da columna a la plantilla, así que el día que haya dos
#: idiomas por empresa el esquema ya está; hoy hay uno y es éste.
IDIOMA_POR_DEFECTO = "es_AR"


def _exigir_administrador(rol: RolUsuario) -> None:
    if rol is not RolUsuario.ADMINISTRADOR:
        raise EntradaInvalida(MOTIVO_SOLO_ADMIN)


class ListarPlantillas:
    """PAN-CFG-NOT. Todos los roles leen, y **siembra las que falten**.

    Ver el docstring del módulo: sembrar acá y no en el alta de la empresa es lo que hace que
    las empresas creadas antes de este épico también las tengan.
    """

    def __init__(self, plantillas: PortRepositorioPlantillas) -> None:
        self._plantillas = plantillas

    async def ejecutar(
        self, *, empresa_id: EmpresaId, ahora: datetime
    ) -> list[PlantillaDeNotificacion]:
        existentes = await self._plantillas.listar()
        conocidos = {una.codigo for una in existentes}
        faltantes = [
            PlantillaDeNotificacion(
                id=uuid4(),
                empresa_id=empresa_id,
                codigo=codigo,
                canal=canal,
                idioma=IDIOMA_POR_DEFECTO,
                cuerpo=cuerpo,
                # `PENDIENTE` y no `APROBADA`: nadie le preguntó todavía a Meta, y decir que
                # está aprobada sería afirmar algo que sólo el proveedor puede afirmar.
                estado_aprobacion=(
                    EstadoDeAprobacion.PENDIENTE
                    if canal is CanalNotificacion.WHATSAPP
                    else EstadoDeAprobacion.NO_APLICA
                ),
                created_at=ahora,
                updated_at=ahora,
            )
            for codigo, (canal, cuerpo) in DE_FABRICA.items()
            if codigo not in conocidos
        ]
        for plantilla in faltantes:
            await self._plantillas.agregar(plantilla)
        return sorted([*existentes, *faltantes], key=lambda una: una.codigo)


class EditarPlantilla:
    """HU-E11-02, segundo y tercer criterio.

    La validación de variables la hace el agregado, con la frase de la historia. No se repite
    acá: dos lugares que validan lo mismo son dos lugares que pueden dejar de estar de acuerdo.
    """

    def __init__(
        self, plantillas: PortRepositorioPlantillas, publicador: PublicadorDeEventos
    ) -> None:
        self._plantillas = plantillas
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        plantilla_id: UUID,
        cuerpo: str,
        ahora: datetime,
    ) -> PlantillaDeNotificacion:
        _exigir_administrador(rol)
        plantilla = await self._plantillas.buscar_por_id(plantilla_id)
        if plantilla is None:
            raise EntradaInvalida("La plantilla no existe")
        plantilla.editar(cuerpo, ahora)
        await self._plantillas.guardar(plantilla)
        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                ocurrido_en=ahora,
                modulo=Modulo.BUSINESS_CONFIG,
                accion="editar_plantilla",
                entidad_afectada=f"PlantillaDeNotificacion:{plantilla.id}",
                resultado=Resultado.COMPLETADO,
            )
        )
        return plantilla


class ResolverPlantilla:
    """El texto listo para mandar, o `None` si no hay plantilla usable.

    `None` cubre los tres casos que para el llamador significan lo mismo: no existe, no está
    aprobada, o el código no está configurado. En los tres, el adaptador manda su texto de
    fábrica — ver el docstring del módulo.
    """

    def __init__(self, plantillas: PortRepositorioPlantillas) -> None:
        self._plantillas = plantillas

    async def ejecutar(self, codigo: str, variables: dict[str, str]) -> str | None:
        plantilla = await self._plantillas.buscar_por_codigo(codigo)
        if plantilla is None or not plantilla.puede_usarse:
            return None
        try:
            return plantilla.resolver(variables)
        except EntradaInvalida:
            return None


def variables_conocidas(codigo: str) -> frozenset[str]:
    """Las que la pantalla ofrece como ayuda al editar. Lectura, no validación."""
    return VARIABLES_POR_CODIGO.get(codigo, frozenset())


__all__ = [
    "DE_FABRICA",
    "IDIOMA_POR_DEFECTO",
    "EditarPlantilla",
    "ListarPlantillas",
    "ResolverPlantilla",
    "variables_conocidas",
]
