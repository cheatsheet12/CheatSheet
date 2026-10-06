"""`PlantillaDeNotificacion` — el texto que el sistema le manda a alguien (HU-E11-02).

Tres reglas viven acá, y las tres salen de la historia:

1. **Las variables se validan contra un catálogo por código** (RN-02 y el tercer criterio).
   Cada plantilla sabe qué variables admite: `{{nombre}}` en un recordatorio de turno es
   legítimo y en uno de cobro puede no serlo. Aceptar cualquier variable haría que el mensaje
   saliera con un `{{fehca_del_turno}}` literal al cliente — que es exactamente lo que la
   validación de la historia evita.

2. **Una plantilla de WhatsApp no aprobada no se puede usar por ese canal** (RN-03, RN-04).
   Meta aprueba las plantillas de mensajes iniciados por la empresa, y mandar una sin aprobar
   no falla en silencio: falla con el mensaje sin entregar y la cuenta un poco más cerca de una
   sanción.

3. **El reemplazo es literal y no evalúa nada.** `{{variable}}` se cambia por su valor y punto.
   No hay condicionales, ni bucles, ni expresiones: un motor de plantillas dentro de un texto
   que un administrador edita es una superficie de ejecución que este sistema no necesita.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from cheatsheet.contexts.business_config.domain.regla import CanalNotificacion
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.zona_horaria import ZONA_ARGENTINA

#: HU-E11-02, tercer criterio, palabra por palabra.
MENSAJE_VARIABLE_INVALIDA = "La variable indicada no es válida para esta plantilla."
MENSAJE_SIN_APROBAR = (
    "La plantilla no está aprobada por Meta y no puede usarse para el canal de WhatsApp."
)
#: Meta rechaza una plantilla que empieza o termina con un parámetro (U6, [T-REV]).
MENSAJE_BORDE_CON_VARIABLE = "Meta no acepta una plantilla que empiece o termine con una variable."
MENSAJE_EN_REVISION = (
    "La plantilla está en revisión de Meta. Vas a poder editarla cuando Meta responda."
)

#: Meta permite editar una plantilla aprobada una vez cada 24 h [T-MGMT].
ESPERA_ENTRE_EDICIONES = timedelta(hours=24)

#: `<nombre>_v2`, `_v3`…: el nombre versionado de una plantilla que hubo que crear de nuevo.
PATRON_DE_VERSION = re.compile(r"^(.*)_v(\d+)$")

#: `{{nombre_de_variable}}`. Dos llaves y un identificador: nada que se pueda confundir con
#: código, y nada que un texto normal escriba por accidente.
PATRON_DE_VARIABLE = re.compile(r"\{\{([a-z_][a-z0-9_]*)\}\}")


class EstadoDeAprobacion(StrEnum):
    """El `estado_aprobacion_meta` del DER, que ahí es un `varchar` libre.

    Enum acá porque **gobierna una decisión** —RN-04 impide usar la no aprobada— y una decisión
    que depende de comparar contra cadenas sueltas es una decisión que un día compara contra la
    cadena mal escrita.

    `NO_APLICA` es el caso de los canales que no piden aprobación: email y panel. No es un
    estado de Meta, es la ausencia de Meta.
    """

    NO_APLICA = "NO_APLICA"
    #: Nunca la aceptó Meta: todavía no se mandó, o la última creación fue refutada.
    SIN_ENVIAR = "SIN_ENVIAR"
    PENDIENTE = "PENDIENTE"
    APROBADA = "APROBADA"
    RECHAZADA = "RECHAZADA"
    PAUSADA = "PAUSADA"
    DESHABILITADA = "DESHABILITADA"


#: Qué variables admite cada código de plantilla.
#:
#: Una tabla y no un campo por plantilla: las variables las decide **quien manda el mensaje**,
#: no quien lo redacta. Un administrador no puede inventar `{{saldo}}` en un recordatorio de
#: turno porque del otro lado nadie se lo va a pasar, y el mensaje saldría con el literal.
VARIABLES_POR_CODIGO: dict[str, frozenset[str]] = {
    "turno_confirmado": frozenset({"nombre", "servicio", "recurso", "fecha", "hora"}),
    "turno_cancelado": frozenset({"nombre", "servicio", "fecha", "hora"}),
    "turno_reprogramado": frozenset(
        {"nombre", "servicio", "fecha", "hora", "fecha_anterior", "hora_anterior"}
    ),
    "recordatorio_de_turno": frozenset({"nombre", "servicio", "fecha", "hora"}),
    "recordatorio_de_cobro": frozenset({"nombre", "monto", "concepto", "link", "vencimiento"}),
    "cobro_generado": frozenset({"nombre", "monto", "concepto", "link"}),
}


#: Un valor ficticio por variable, para que Meta revise el texto con algo parecido a un mensaje
#: real. **Datos inventados** (`CLAUDE.md` §3): nunca el de un cliente.
EJEMPLOS_DE_VARIABLES: dict[str, str] = {
    "nombre": "Ana",
    "servicio": "Consulta general",
    "recurso": "Sala 1",
    "fecha": "15/10/2026",
    "hora": "10:30",
    "fecha_anterior": "14/10/2026",
    "hora_anterior": "09:00",
    "monto": "12.500,00",
    "concepto": "Cuota de octubre",
    "vencimiento": "10/10/2026",
    "link": "https://pagos.example.com/c/abc123",
}


def variables_de(cuerpo: str) -> frozenset[str]:
    """Las variables que un texto usa. Sin evaluar nada — es una expresión regular."""
    return frozenset(PATRON_DE_VARIABLE.findall(cuerpo))


def ejemplos_de(codigo: str) -> dict[str, str]:
    """Un ejemplo ficticio por cada variable que el código admite."""
    return {
        variable: EJEMPLOS_DE_VARIABLES[variable]
        for variable in sorted(VARIABLES_POR_CODIGO.get(codigo, frozenset()))
    }


def empieza_o_termina_con_variable(cuerpo: str) -> bool:
    """Lo que Meta no acepta en el borde de una plantilla."""
    texto = cuerpo.strip()
    return bool(
        re.match(PATRON_DE_VARIABLE, texto) or re.search(PATRON_DE_VARIABLE.pattern + r"\Z", texto)
    )


@dataclass(slots=True)
class PlantillaDeNotificacion:
    """Un texto parametrizado, con su canal, su idioma y su estado ante Meta."""

    id: UUID
    empresa_id: EmpresaId
    codigo: str
    canal: CanalNotificacion
    idioma: str
    cuerpo: str
    estado_aprobacion: EstadoDeAprobacion = EstadoDeAprobacion.NO_APLICA
    created_at: datetime | None = None
    updated_at: datetime | None = None
    #: Lo que se sabe de la plantilla del otro lado (U6). Nada de esto lo decide el administrador.
    nombre_en_meta: str | None = None
    meta_plantilla_id: str | None = None
    motivo_meta: str | None = None
    detalle_meta: str | None = None
    categoria_en_meta: str | None = None
    enviada_a_meta_en: datetime | None = None
    estado_meta_en: datetime | None = None

    def __post_init__(self) -> None:
        # Las variables se validan siempre; el borde del texto, solo al crear y al editar: una
        # fila editada antes de que Meta pidiera esta regla tiene que poder leerse, y la
        # pantalla le muestra el motivo del rechazo en vez de un error al listar.
        if not self.codigo.strip() or not self.cuerpo.strip():
            raise EntradaInvalida("Una plantilla necesita código y cuerpo")
        self._exigir_variables_validas(self.cuerpo)

    @classmethod
    def nueva(
        cls,
        *,
        id: UUID,
        empresa_id: EmpresaId,
        codigo: str,
        canal: CanalNotificacion,
        idioma: str,
        cuerpo: str,
        ahora: datetime,
    ) -> PlantillaDeNotificacion:
        """Una plantilla recién sembrada. WhatsApp nace `SIN_ENVIAR`: nadie se la mandó a Meta."""
        es_whatsapp = canal is CanalNotificacion.WHATSAPP
        plantilla = cls(
            id=id,
            empresa_id=empresa_id,
            codigo=codigo,
            canal=canal,
            idioma=idioma,
            cuerpo=cuerpo,
            estado_aprobacion=(
                EstadoDeAprobacion.SIN_ENVIAR if es_whatsapp else EstadoDeAprobacion.NO_APLICA
            ),
            created_at=ahora,
            updated_at=ahora,
            nombre_en_meta=codigo if es_whatsapp else None,
        )
        plantilla._exigir_bordes_validos(cuerpo)
        return plantilla

    @property
    def variables_admitidas(self) -> frozenset[str]:
        """Las que su código admite. Un código desconocido no admite ninguna.

        Deliberado: una plantilla con un código que el sistema no manda nunca es una plantilla
        que nadie va a usar, y dejarle poner variables libres sería prometerle a alguien que
        va a funcionar.
        """
        return VARIABLES_POR_CODIGO.get(self.codigo, frozenset())

    def editar(self, cuerpo: str, momento: datetime) -> None:
        """Cambia el texto si la edición es admisible ante Meta (RN-02, U6).

        **No inventa un estado**: el que queda lo escribe solo `aplicar_respuesta_de_meta` con lo
        que Meta conteste, porque editar reenvía la plantilla y el resultado es de Meta. Lo que sí
        decide acá es si la edición se puede mandar: el texto no empieza ni termina con una
        variable, una `PENDIENTE` está en revisión y no se toca, y una aprobada se edita una vez
        cada 24 h [T-MGMT].
        """
        self._exigir_variables_validas(cuerpo)
        self._exigir_bordes_validos(cuerpo)
        if self.es_de_whatsapp:
            self._exigir_edicion_admisible(momento)
        self.cuerpo = cuerpo
        self.updated_at = momento

    @property
    def es_de_whatsapp(self) -> bool:
        return self.canal is CanalNotificacion.WHATSAPP

    @property
    def editable_desde(self) -> datetime | None:
        """Cuándo se puede volver a editar una aprobada, o `None` si no hay espera."""
        if (
            self.es_de_whatsapp
            and self.estado_aprobacion is EstadoDeAprobacion.APROBADA
            and self.enviada_a_meta_en is not None
        ):
            return self.enviada_a_meta_en + ESPERA_ENTRE_EDICIONES
        return None

    def nombre_para_crear(self) -> str:
        """El nombre con el que se crea en Meta: el guardado, o uno versionado si ya se usó.

        Meta bloquea 30 días el nombre de una plantilla borrada y no se puede reutilizar uno
        deshabilitado: ahí la plantilla se crea de nuevo como `<nombre>_v2`, `_v3`…
        """
        ya_se_envio = self.enviada_a_meta_en is not None and self.meta_plantilla_id is None
        if self.estado_aprobacion is EstadoDeAprobacion.DESHABILITADA or ya_se_envio:
            return self.siguiente_nombre()
        return self.nombre_en_meta or self.codigo

    def siguiente_nombre(self, desde: str | None = None) -> str:
        """`recordatorio_de_turno` → `…_v2` → `…_v3`. `desde` es el nombre recién probado."""
        actual = desde or self.nombre_en_meta or self.codigo
        coincidencia = PATRON_DE_VERSION.match(actual)
        if coincidencia is None:
            return f"{actual}_v2"
        return f"{coincidencia.group(1)}_v{int(coincidencia.group(2)) + 1}"

    def exigir_enviable(self) -> None:
        """Lo que se puede mandar a Meta sin editar: el texto actual cumple sus reglas."""
        self._exigir_bordes_validos(self.cuerpo)

    def vincular_con_meta(self, meta_plantilla_id: str) -> None:
        """La encontramos en Meta por nombre (una creación cuya respuesta se perdió)."""
        self.meta_plantilla_id = meta_plantilla_id

    def registrar_envio_a_meta(
        self, *, meta_plantilla_id: str, nombre_en_meta: str, momento: datetime
    ) -> None:
        """Meta aceptó crear o editar: guarda su id, el nombre y cuándo se mandó."""
        self.meta_plantilla_id = meta_plantilla_id
        self.nombre_en_meta = nombre_en_meta
        self.enviada_a_meta_en = momento
        # Lo que Meta dijo antes de este envío ya no vale: el estado nuevo lo escribe la respuesta
        # de este envío, no se descarta por un reloj de Meta apenas adelantado al nuestro.
        self.estado_meta_en = None
        self.updated_at = momento

    def aplicar_respuesta_de_meta(
        self,
        estado: EstadoDeAprobacion,
        *,
        motivo: str | None,
        detalle: str | None,
        momento: datetime,
        categoria: str | None = None,
    ) -> bool:
        """Lo único que escribe el estado. Idempotente, y no retrocede ante un evento viejo.

        `momento` es cuándo Meta dijo esto (el `time` del webhook, o el de la consulta): un
        `PENDING` que llega tarde, después de un `APPROVED`, se ignora. Devuelve si algo cambió.
        """
        if self.estado_meta_en is not None and momento < self.estado_meta_en:
            return False
        nuevo = (
            estado,
            motivo if estado is not EstadoDeAprobacion.APROBADA else None,
            detalle,
            categoria or self.categoria_en_meta,
            None if estado is EstadoDeAprobacion.SIN_ENVIAR else self.meta_plantilla_id,
        )
        actual = (
            self.estado_aprobacion,
            self.motivo_meta,
            self.detalle_meta,
            self.categoria_en_meta,
            self.meta_plantilla_id,
        )
        self.estado_meta_en = momento
        if nuevo == actual:
            return False
        (
            self.estado_aprobacion,
            self.motivo_meta,
            self.detalle_meta,
            self.categoria_en_meta,
            self.meta_plantilla_id,
        ) = nuevo
        self.updated_at = momento
        return True

    def marcar_sin_enviar(self, detalle: str, momento: datetime) -> None:
        """No hubo a quién mandársela (WhatsApp sin conectar): queda a la vista, sin inventar."""
        self.estado_aprobacion = EstadoDeAprobacion.SIN_ENVIAR
        self.motivo_meta = None
        self.detalle_meta = detalle
        self.updated_at = momento

    @property
    def puede_usarse(self) -> bool:
        """RN-04: una plantilla no aprobada no sirve para el canal que exige aprobación."""
        if self.canal is not CanalNotificacion.WHATSAPP:
            return True
        return self.estado_aprobacion is EstadoDeAprobacion.APROBADA

    def resolver(self, variables: dict[str, str]) -> str:
        """El cuerpo con las variables reemplazadas.

        Una variable que la plantilla usa y el llamador no pasó queda **como está**, con sus
        llaves. Es feo a propósito: un valor vacío escondería el error y el cliente recibiría
        «tu turno del  a las », mientras que el literal se ve en el primer envío de prueba.
        """
        if not self.puede_usarse:
            raise EntradaInvalida(MENSAJE_SIN_APROBAR)

        def cambiar(coincidencia: re.Match[str]) -> str:
            return variables.get(coincidencia.group(1), coincidencia.group(0))

        return PATRON_DE_VARIABLE.sub(cambiar, self.cuerpo)

    def _exigir_bordes_validos(self, cuerpo: str) -> None:
        if self.es_de_whatsapp and empieza_o_termina_con_variable(cuerpo):
            raise EntradaInvalida(MENSAJE_BORDE_CON_VARIABLE)

    def _exigir_edicion_admisible(self, momento: datetime) -> None:
        if self.estado_aprobacion is EstadoDeAprobacion.PENDIENTE:
            raise EntradaInvalida(MENSAJE_EN_REVISION)
        desde = self.editable_desde
        if desde is not None and momento < desde:
            local = desde.astimezone(ZONA_ARGENTINA)
            raise EntradaInvalida(
                "Meta permite editar una plantilla aprobada una vez cada 24 horas. "
                f"Vas a poder editarla a partir del {local:%d/%m/%Y} a las {local:%H:%M}."
            )

    def _exigir_variables_validas(self, cuerpo: str) -> None:
        desconocidas = variables_de(cuerpo) - self.variables_admitidas
        if desconocidas:
            # La frase de la historia, letra por letra. El nombre de la variable no se
            # concatena: el criterio de aceptación fija el mensaje exacto.
            raise EntradaInvalida(MENSAJE_VARIABLE_INVALIDA)


__all__ = [
    "EJEMPLOS_DE_VARIABLES",
    "ESPERA_ENTRE_EDICIONES",
    "MENSAJE_BORDE_CON_VARIABLE",
    "MENSAJE_EN_REVISION",
    "MENSAJE_SIN_APROBAR",
    "MENSAJE_VARIABLE_INVALIDA",
    "VARIABLES_POR_CODIGO",
    "EstadoDeAprobacion",
    "PlantillaDeNotificacion",
    "ejemplos_de",
    "empieza_o_termina_con_variable",
    "variables_de",
]
