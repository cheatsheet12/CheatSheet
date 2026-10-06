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

import re
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from cheatsheet.contexts.business_config.application.ports import PortRepositorioPlantillas
from cheatsheet.contexts.business_config.domain.estados_de_meta import (
    EVENTOS_QUE_SE_RELEEN,
    estado_desde_evento,
    estado_desde_nodo,
)
from cheatsheet.contexts.business_config.domain.plantilla import (
    PATRON_DE_VARIABLE,
    VARIABLES_POR_CODIGO,
    PlantillaDeNotificacion,
)
from cheatsheet.contexts.business_config.domain.regla import CanalNotificacion
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.roles import RolUsuario

logger = obtener_logger(__name__)

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
        "Podés pagarlo acá: {{link}} Gracias.",
    ),
    "cobro_generado": (
        CanalNotificacion.WHATSAPP,
        "Hola {{nombre}}, te dejamos el link para pagar {{concepto}} por $ {{monto}}: "
        "{{link}} Gracias.",
    ),
}

#: El idioma de fábrica. El DER le da columna a la plantilla, así que el día que haya dos
#: idiomas por empresa el esquema ya está; hoy hay uno y es éste.
IDIOMA_POR_DEFECTO = "es_AR"


def exigir_administrador(rol: RolUsuario) -> None:
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
            # `SIN_ENVIAR` y no `PENDIENTE` ni `APROBADA`: nadie se la mandó todavía a Meta, y
            # decir otra cosa sería afirmar algo que sólo el proveedor puede afirmar.
            PlantillaDeNotificacion.nueva(
                id=uuid4(),
                empresa_id=empresa_id,
                codigo=codigo,
                canal=canal,
                idioma=IDIOMA_POR_DEFECTO,
                cuerpo=cuerpo,
                ahora=ahora,
            )
            for codigo, (canal, cuerpo) in DE_FABRICA.items()
            if codigo not in conocidos
        ]
        for plantilla in faltantes:
            await self._plantillas.agregar(plantilla)
        return sorted([*existentes, *faltantes], key=lambda una: una.codigo)


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


#: Meta no acepta saltos de línea ni tabulaciones dentro de un valor de parámetro (regla conocida,
#: sin verificar en la documentación consultada: `docs/aidlc/TODO.md` §22.47).
SALTOS_Y_TABULACIONES = re.compile(r"[\r\n\t]+")


def limpiar_valor(valor: str) -> str:
    """Un valor listo para viajar como parámetro: sin saltos de línea ni tabulaciones."""
    return SALTOS_Y_TABULACIONES.sub(" ", valor).strip()


@dataclass(frozen=True, slots=True)
class PlantillaParaEnviar:
    """Lo que un adaptador necesita para mandar una plantilla aprobada (OHS de `business_config`).

    `parametros` son **solo** las variables que el cuerpo usa (Meta exige la cantidad exacta, error
    132000). `texto` es el cuerpo resuelto, para guardarlo como lo que se mandó.
    """

    nombre_en_meta: str
    idioma: str
    parametros: dict[str, str]
    texto: str


class ConsultarPlantillaParaEnviar:
    """La plantilla **aprobada** de un código, lista para mandar, o `None`.

    `None` cubre lo que para el adaptador significa lo mismo: no existe, no está aprobada por Meta,
    no es de WhatsApp o el llamador no pasó una variable que el cuerpo usa. En todos, el adaptador
    manda su texto de fábrica. Una plantilla no aprobada no se usa jamás (RN-04).
    """

    def __init__(self, plantillas: PortRepositorioPlantillas) -> None:
        self._plantillas = plantillas

    async def ejecutar(self, codigo: str, variables: dict[str, str]) -> PlantillaParaEnviar | None:
        plantilla = await self._plantillas.buscar_por_codigo(codigo)
        if plantilla is None or not plantilla.es_de_whatsapp or not plantilla.puede_usarse:
            return None
        usadas = list(dict.fromkeys(PATRON_DE_VARIABLE.findall(plantilla.cuerpo)))
        if any(variable not in variables for variable in usadas):
            logger.warning("plantilla_con_variables_sin_valor", codigo=codigo)
            return None
        limpias = {variable: limpiar_valor(variables[variable]) for variable in usadas}
        return PlantillaParaEnviar(
            nombre_en_meta=plantilla.nombre_en_meta or plantilla.codigo,
            idioma=plantilla.idioma,
            parametros=limpias,
            texto=plantilla.resolver(limpias),
        )


class ActualizarEstadoDesdeMeta:
    """Aplica un estado que Meta informó (webhook o conciliación) a la plantilla de la empresa.

    **Idempotente**: el mismo estado dos veces es un efecto, y uno más viejo que el aplicado no
    retrocede (lo decide el agregado). Sin rol: lo llama el webhook o el barrido, como
    `ConsultarReglasVigentes`. Devuelve si cambió algo.
    """

    def __init__(self, plantillas: PortRepositorioPlantillas) -> None:
        self._plantillas = plantillas

    async def ejecutar(
        self,
        *,
        estado: str,
        momento: datetime,
        es_evento: bool,
        meta_plantilla_id: str | None = None,
        nombre: str | None = None,
        idioma: str | None = None,
        motivo: str | None = None,
        detalle: str | None = None,
    ) -> bool:
        plantilla = await self._buscar(meta_plantilla_id, nombre, idioma)
        if plantilla is None:
            logger.info("plantilla_de_meta_sin_fila_nuestra")
            return False
        if es_evento and estado in EVENTOS_QUE_SE_RELEEN:
            logger.info("plantilla_estado_meta_se_relee", estado=estado)
            return False
        nuevo = estado_desde_evento(estado) if es_evento else estado_desde_nodo(estado)
        if nuevo is None:
            logger.warning("plantilla_estado_meta_desconocido", estado=estado)
            return False
        if meta_plantilla_id and plantilla.meta_plantilla_id != meta_plantilla_id:
            plantilla.vincular_con_meta(meta_plantilla_id)
        cambio = plantilla.aplicar_respuesta_de_meta(
            nuevo, motivo=motivo, detalle=detalle, momento=momento
        )
        await self._plantillas.guardar(plantilla)
        return cambio

    async def _buscar(
        self, meta_plantilla_id: str | None, nombre: str | None, idioma: str | None
    ) -> PlantillaDeNotificacion | None:
        if meta_plantilla_id:
            plantilla = await self._plantillas.buscar_por_meta_id(meta_plantilla_id)
            if plantilla is not None:
                return plantilla
        if nombre and idioma:
            plantilla = await self._plantillas.buscar_por_nombre_en_meta(nombre, idioma)
            if (
                plantilla is not None
                and meta_plantilla_id
                and plantilla.meta_plantilla_id not in (None, meta_plantilla_id)
            ):
                # Mismo nombre, otro id: es otra plantilla de Meta, no la que tenemos vinculada.
                logger.warning("plantilla_de_meta_con_otro_id")
                return None
            return plantilla
        return None


def variables_conocidas(codigo: str) -> frozenset[str]:
    """Las que la pantalla ofrece como ayuda al editar. Lectura, no validación."""
    return VARIABLES_POR_CODIGO.get(codigo, frozenset())


__all__ = [
    "DE_FABRICA",
    "IDIOMA_POR_DEFECTO",
    "MOTIVO_SOLO_ADMIN",
    "ActualizarEstadoDesdeMeta",
    "ConsultarPlantillaParaEnviar",
    "ListarPlantillas",
    "PlantillaParaEnviar",
    "ResolverPlantilla",
    "exigir_administrador",
    "limpiar_valor",
    "variables_conocidas",
]
