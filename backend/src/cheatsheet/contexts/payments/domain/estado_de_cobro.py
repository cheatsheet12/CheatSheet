"""Los tipos y las constantes del cobro: estados, transiciones, medio de pago y link.

Separado de `cobro.py` (que los reexporta) para que cada archivo del dominio quepa en las 400
líneas de `CLAUDE.md` §5. Nada acá tiene comportamiento propio salvo `LinkDePago`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

from cheatsheet.shared.errors import EntradaInvalida

#: Cuánto dura un link de pago sin vencer, cuando nadie dice otra cosa. Treinta días es lo que
#: MercadoPago deja abierta una preferencia sin tocarla, y ponerlo más largo sería un link que
#: el proveedor invalida antes que nosotros — un cobro «pendiente» que ya no se puede pagar.
VIGENCIA_POR_DEFECTO = timedelta(days=30)

#: Cuánto se le perdona al reloj de MercadoPago frente al nuestro: una fecha de aprobación hasta
#: cinco minutos «en el futuro» es desfase de relojes, no un dato inventado. Más allá, no se toma.
TOLERANCIA_DE_RELOJ = timedelta(minutes=5)

#: HU-E6-03, HU-E6-04 y HU-E6-05, palabra por palabra. Constantes porque las historias las
#: escriben y los tests las afirman.
MENSAJE_SIN_CONCEPTO = "Debe ingresar un concepto para el cobro."
MENSAJE_MONTO_NO_POSITIVO = "El monto debe ser mayor a cero."
MENSAJE_PAGADO_NO_CANCELABLE = (
    "Un cobro pagado no puede cancelarse. Si corresponde, emita un reembolso."
)
MENSAJE_MOTIVO_CORTO = "El motivo debe tener al menos 10 caracteres."
MENSAJE_SOLO_PAGADOS_SE_REEMBOLSAN = "Solo pueden reembolsarse cobros pagados."
MENSAJE_REEMBOLSO_EXCEDIDO = (
    "El monto a reembolsar no puede superar el monto pendiente de reembolso del cobro."
)
MENSAJE_REEMBOLSO_EN_PROCESO = "Este cobro ya tiene un reembolso en proceso."
MENSAJE_SIN_REEMBOLSO_EN_PROCESO = "Este cobro no tiene un reembolso en proceso."
MENSAJE_REEMBOLSO_POR_API_SOLO_LINK = "Solo un cobro pagado por link se reembolsa por MercadoPago."
MENSAJE_REEMBOLSO_MANUAL_SOLO_TRANSFERENCIA = (
    "Solo un cobro pagado por transferencia admite registrar el reembolso a mano."
)
MENSAJE_FECHA_FUTURA = "La fecha de devolucion no puede ser posterior a hoy."
MENSAJE_FECHA_ANTERIOR_AL_PAGO = "La fecha de devolucion no puede ser anterior a la del pago."
MENSAJE_REEMBOLSO_NO_CORREGIBLE = (
    "Solo se corrige un reembolso manual que no sea una correccion ni haya sido corregido."
)

#: HU-E6-04 RN-02. Diez caracteres no es una cifra mágica: es lo que hace que «ok» y «error»
#: no pasen, y lo que la historia pide textualmente.
LARGO_MINIMO_DE_MOTIVO = 10


class EstadoCobro(StrEnum):
    """El enum `estado_cobro` del DER, con la etiqueta de interfaz que le corresponde.

    Los nombres de dominio y los de pantalla **no coinciden a propósito**, y las historias lo
    dicen explícitamente: `APROBADO` se muestra «Pagado» y `VENCIDO` se muestra «En mora». El
    dominio es la fuente de verdad; la etiqueta es presentación y vive en el frontend.
    """

    PENDIENTE = "PENDIENTE"
    APROBADO = "APROBADO"
    VENCIDO = "VENCIDO"
    CANCELADO = "CANCELADO"
    REEMBOLSADO_PARCIAL = "REEMBOLSADO_PARCIAL"
    REEMBOLSADO = "REEMBOLSADO"


class MedioDePago(StrEnum):
    """Por dónde entró la plata de un cobro (ADR-0010, punto 1).

    Vocabulario **propio y cerrado**: el de MercadoPago (`payment_type_id`, `payment_method_id`)
    se queda en el ACL de `infrastructure/pasarela.py`. Un cobro nace como link y pasa a
    `TRANSFERENCIA` recién cuando una transferencia lo confirma (unidad `cobro-por-transferencia`).
    """

    LINK_MERCADOPAGO = "LINK_MERCADOPAGO"
    TRANSFERENCIA = "TRANSFERENCIA"


#: Qué transiciones existen. Escritas como tabla por lo que dice `TareaAsincrona`: una máquina
#: de estados desparramada en diez `if` es una máquina que nadie puede revisar.
#:
#: **`APROBADO → APROBADO` está ausente, y esa ausencia es la que trabaja.** Es lo que hace
#: idempotente el webhook de HS-T1 sin depender de nada externo: una notificación repetida
#: encuentra el cobro ya aprobado y no mueve nada. `mp_payment_id` con índice único es la
#: segunda línea; ésta es la primera.
#:
#: **`VENCIDO → APROBADO` existe.** Alguien puede pagar un link vencido de hecho pero no de
#: derecho: MercadoPago acepta el pago mientras la preferencia viva, y rechazarlo acá dejaría
#: plata cobrada sin cobro que la explique.
TRANSICIONES_LEGALES: dict[EstadoCobro, frozenset[EstadoCobro]] = {
    EstadoCobro.PENDIENTE: frozenset(
        {EstadoCobro.APROBADO, EstadoCobro.VENCIDO, EstadoCobro.CANCELADO}
    ),
    EstadoCobro.VENCIDO: frozenset({EstadoCobro.APROBADO, EstadoCobro.CANCELADO}),
    # El estado tras un reembolso o una corrección se **deriva** del acumulado
    # (`_estado_por_acumulado`, ADR-0010 punto 5): las transiciones que bajan solo las alcanza
    # una corrección.
    EstadoCobro.APROBADO: frozenset({EstadoCobro.REEMBOLSADO_PARCIAL, EstadoCobro.REEMBOLSADO}),
    EstadoCobro.REEMBOLSADO_PARCIAL: frozenset(
        {EstadoCobro.REEMBOLSADO_PARCIAL, EstadoCobro.REEMBOLSADO, EstadoCobro.APROBADO}
    ),
    EstadoCobro.REEMBOLSADO: frozenset({EstadoCobro.REEMBOLSADO_PARCIAL, EstadoCobro.APROBADO}),
    EstadoCobro.CANCELADO: frozenset(),
}


@dataclass(frozen=True, slots=True)
class LinkDePago:
    """La preferencia de MercadoPago y su URL (HU-E6-03 RN-01).

    Frozen, y sin método para cambiarla. Un cobro tiene **un solo link activo a la vez**
    (RN-04): generar otro reemplaza el objeto entero, que es lo que hace que «invalidar el
    anterior» sea imposible de olvidar.
    """

    preference_id: str
    url: str

    def __post_init__(self) -> None:
        if not self.preference_id.strip() or not self.url.strip():
            raise EntradaInvalida("Un link de pago necesita preferencia y URL")


__all__ = [
    "LARGO_MINIMO_DE_MOTIVO",
    "MENSAJE_FECHA_ANTERIOR_AL_PAGO",
    "MENSAJE_FECHA_FUTURA",
    "MENSAJE_MONTO_NO_POSITIVO",
    "MENSAJE_MOTIVO_CORTO",
    "MENSAJE_PAGADO_NO_CANCELABLE",
    "MENSAJE_REEMBOLSO_EN_PROCESO",
    "MENSAJE_REEMBOLSO_EXCEDIDO",
    "MENSAJE_REEMBOLSO_MANUAL_SOLO_TRANSFERENCIA",
    "MENSAJE_REEMBOLSO_NO_CORREGIBLE",
    "MENSAJE_REEMBOLSO_POR_API_SOLO_LINK",
    "MENSAJE_SIN_CONCEPTO",
    "MENSAJE_SIN_REEMBOLSO_EN_PROCESO",
    "MENSAJE_SOLO_PAGADOS_SE_REEMBOLSAN",
    "TOLERANCIA_DE_RELOJ",
    "TRANSICIONES_LEGALES",
    "VIGENCIA_POR_DEFECTO",
    "EstadoCobro",
    "LinkDePago",
    "MedioDePago",
]
