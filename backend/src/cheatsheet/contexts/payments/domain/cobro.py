"""`Cobro` — plata real, y la máquina de estados que la mantiene honesta.

Este contexto es Core por una razón sola: **mueve dinero**. Un cobro mal aprobado es una
deuda que el sistema da por saldada; un reembolso mal calculado es plata que sale de la
cuenta de la empresa. Las dos cosas se descubren tarde y se arreglan con MercadoPago.

Tres invariantes viven acá:

1. **La plata es `Decimal` y se redondea explícitamente.** Mismo criterio que `billing`
   (decisión D15 del épico 5): dos decimales, `ROUND_HALF_UP`, y el redondeo en un solo lugar.
2. **`APROBADO` es terminal salvo por el reembolso.** Un cobro pagado no se cancela
   (HU-E6-04 RN-01) — se reembolsa, que es otra operación con otro actor y otro efecto.
3. **La idempotencia del webhook empieza acá.** `aprobar` se niega a aprobar dos veces, y
   `registrar_pago` guarda el `mp_payment_id` que el índice único de la migración 0019
   convierte en una garantía (decisión **D20**).

**El reembolso en vuelo no es un estado** (decisión **D27**). El enum del DER no lo tiene y no
se le agrega: un reembolso rechazado tiene que dejar el cobro en `APROBADO` (RN-03), y volver
a un estado anterior es exactamente la forma que la máquina de estados del épico 5 evita. Lo
que existe es `reembolso_solicitado_en`, y la pantalla dice «Reembolso en proceso» a partir de
eso.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from uuid import UUID

from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

CENTAVOS = Decimal("0.01")

#: Cuánto dura un link de pago sin vencer, cuando nadie dice otra cosa. Treinta días es lo que
#: MercadoPago deja abierta una preferencia sin tocarla, y ponerlo más largo sería un link que
#: el proveedor invalida antes que nosotros — un cobro «pendiente» que ya no se puede pagar.
VIGENCIA_POR_DEFECTO = timedelta(days=30)

#: HU-E6-03, HU-E6-04 y HU-E6-05, palabra por palabra. Constantes porque las historias las
#: escriben y los tests las afirman.
MENSAJE_SIN_CONCEPTO = "Debe ingresar un concepto para el cobro."
MENSAJE_MONTO_NO_POSITIVO = "El monto debe ser mayor a cero."
MENSAJE_PAGADO_NO_CANCELABLE = (
    "Un cobro pagado no puede cancelarse. Si corresponde, emita un reembolso."
)
MENSAJE_MOTIVO_CORTO = "El motivo debe tener al menos 10 caracteres."
MENSAJE_SOLO_PAGADOS_SE_REEMBOLSAN = "Solo pueden reembolsarse cobros pagados."
MENSAJE_REEMBOLSO_EXCEDIDO = "El monto a reembolsar no puede superar el monto del cobro."

#: HU-E6-04 RN-02. Diez caracteres no es una cifra mágica: es lo que hace que «ok» y «error»
#: no pasen, y lo que la historia pide textualmente.
LARGO_MINIMO_DE_MOTIVO = 10


def redondear(monto: Decimal) -> Decimal:
    """Dos decimales, `ROUND_HALF_UP`. El único lugar donde este contexto redondea plata."""
    return monto.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


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
    REEMBOLSADO = "REEMBOLSADO"


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
    EstadoCobro.APROBADO: frozenset({EstadoCobro.REEMBOLSADO}),
    EstadoCobro.CANCELADO: frozenset(),
    EstadoCobro.REEMBOLSADO: frozenset(),
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


@dataclass(slots=True)
class Cobro:
    """Una deuda con un link para pagarla.

    `descripcion` es el «concepto» de la historia. Se llama así porque así lo llama el DER, y
    la traducción vive en la pantalla — que es donde el usuario lee la palabra.
    """

    id: UUID
    empresa_id: EmpresaId
    cliente_id: UUID
    monto: Decimal
    descripcion: str
    vence_el: datetime
    created_at: datetime
    estado: EstadoCobro = EstadoCobro.PENDIENTE
    link: LinkDePago | None = None
    #: El id del pago en MercadoPago. **Es la clave de idempotencia del webhook** (D20), y por
    #: eso se guarda aunque no lo lea ninguna pantalla.
    mp_payment_id: str | None = None
    comprobante_id: UUID | None = None
    #: Referenciado por id y sin FK (hallazgo H4 del DER): `turno` es de otro contexto. Lo
    #: escribe el épico 7.
    turno_id: UUID | None = None
    pagado_en: datetime | None = None
    monto_reembolsado: Decimal | None = None
    reembolso_solicitado_en: datetime | None = None
    motivo_de_cancelacion: str | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.descripcion.strip():
            raise EntradaInvalida(MENSAJE_SIN_CONCEPTO)
        if self.monto <= 0:
            raise EntradaInvalida(MENSAJE_MONTO_NO_POSITIVO)
        self.monto = redondear(self.monto)

    # ------------------------------------------------------------------ el link

    def asignar_link(self, link: LinkDePago, ahora: datetime) -> None:
        """RN-04: un solo link activo a la vez.

        Reemplazar el objeto **es** invalidar el anterior: no hay una lista de links de la que
        alguien pueda olvidarse de sacar el viejo. Quien genere el segundo tiene que registrar
        el cambio en la bitácora, que es lo que pide el último criterio de HU-E6-03.
        """
        self._exigir_cobrable()
        self.link = link
        self.updated_at = ahora

    @property
    def tiene_link_activo(self) -> bool:
        """Si el link se puede usar **ahora**. RN-03 y RN-04, resueltas por el estado.

        **Nada acá borra la preferencia**, y esa ausencia es deliberada: invalidar un link
        significa dejar de ofrecerlo, no olvidar cuál era. Invalidarlo de verdad es un hecho
        del lado de MercadoPago y lo pide el caso de uso al cancelar (`PortPasarelaDePago.
        invalidar_link`); este agregado sólo deja de considerarlo usable. El
        `mp_preference_id` es lo que ata una notificación de MercadoPago a una fila nuestra
        (D20), así que borrarlo al aprobar dejaría al webhook siguiente sin poder decir a qué
        cobro correspondía — y el log diría «no es de esta empresa» sobre un cobro que sí lo
        es. Es también el rastro que alguien sigue cuando un pago «no entró».

        Reemplazar un link es `asignar_link`, que pisa el objeto entero: no hay una lista de
        la que alguien pueda olvidarse de sacar el viejo.
        """
        return self.link is not None and self.esta_abierto

    # ------------------------------------------------------------------ los estados

    def aprobar(self, *, payment_id: str, ahora: datetime) -> None:
        """MercadoPago confirmó el pago (HS-T1 RN-02).

        **Se niega a aprobar dos veces**, y esa negativa es la primera línea de defensa de la
        idempotencia del webhook: la tabla de transiciones no tiene `APROBADO → APROBADO`. El
        índice único sobre `mp_payment_id` es la segunda.
        """
        self._transicionar(EstadoCobro.APROBADO)
        self.mp_payment_id = payment_id
        self.pagado_en = ahora
        self.updated_at = ahora

    def vencer(self, ahora: datetime) -> None:
        """RN-03 de HU-E6-01, ejecutada por el barrido de la decisión D23.

        Es una transición real y no una propiedad calculada, por tres razones que la decisión
        explica: los recordatorios dependen del estado, la bitácora tiene que registrarlo, y
        el listado filtra por estado en la base.
        """
        self._transicionar(EstadoCobro.VENCIDO)
        self.updated_at = ahora

    def cancelar(self, *, motivo: str, ahora: datetime) -> None:
        """HU-E6-04. Requiere un motivo, desactiva el link y detiene los recordatorios.

        Detener los recordatorios no es una llamada más: es consecuencia del estado. HS-T3
        RN-03 no le manda recordatorios a un `CANCELADO`, así que la cadena se corta sola.

        **Lo que este método no puede hacer es matar el link en MercadoPago**: eso es una
        llamada a un tercero y vive en el caso de uso. Acá el cobro deja de considerarlo
        usable; allá deja de poder cobrarse. Las dos cosas tienen que pasar, y el orden —
        primero esta validación, después la red— es lo que hace que un motivo de nueve
        caracteres no gaste una llamada.
        """
        if self.estado is EstadoCobro.APROBADO:
            # El texto de la historia, que además dice qué hacer en su lugar.
            raise InvarianteViolada(MENSAJE_PAGADO_NO_CANCELABLE)
        if len(motivo.strip()) < LARGO_MINIMO_DE_MOTIVO:
            raise EntradaInvalida(MENSAJE_MOTIVO_CORTO)

        self._transicionar(EstadoCobro.CANCELADO)
        self.motivo_de_cancelacion = motivo.strip()
        # El link no se borra: el estado ya lo desactiva (`tiene_link_activo`), y la
        # preferencia es lo que ata una notificación tardía a esta fila.
        self.updated_at = ahora

    def registrar_pago_huerfano(self, *, payment_id: str, ahora: datetime) -> None:
        """Entró plata por el link de un cobro cancelado. **No hay transición** (HU-E6-04).

        Misma forma que `solicitar_reembolso` (D27): un hecho que se anota sin mover el estado.
        El cobro sigue `CANCELADO` porque alguien lo dio de baja con un motivo escrito, y
        resucitarlo sería contradecir esa decisión con un webhook. Lo que cambia es que el pago
        deja de ser invisible: queda atado a esta fila, y el caso de uso lo publica con
        `Resultado.ERROR` para que alguien lo mire hoy y no cuando concilie el extracto.

        Guardar el `payment_id` es además lo que hace idempotente la notificación repetida:
        `buscar_por_payment_id` lo encuentra y el webhook siguiente corta antes de alertar dos
        veces.
        """
        if self.estado is not EstadoCobro.CANCELADO:
            raise InvarianteViolada("Solo un cobro cancelado puede tener un pago huerfano")
        if self.mp_payment_id is not None:
            raise InvarianteViolada("Este cobro ya tiene un pago registrado")
        self.mp_payment_id = payment_id
        self.updated_at = ahora

    @property
    def tiene_pago_huerfano(self) -> bool:
        """Cancelado y con plata asociada. Lo que PAN-COB-02 muestra en rojo.

        Sin esto, el aviso de severidad alta manda al administrador a una pantalla donde no se
        ve nada raro.
        """
        return self.estado is EstadoCobro.CANCELADO and self.mp_payment_id is not None

    def solicitar_reembolso(self, *, monto: Decimal, ahora: datetime) -> Decimal:
        """HU-E6-05 — pide el reembolso a MercadoPago. **No cambia el estado** (D27).

        El cobro sigue `APROBADO` mientras la solicitud está en vuelo, y lo que la pantalla
        muestra como «Reembolso en proceso» sale de `reembolso_solicitado_en`. Si MercadoPago
        rechaza, no hay nada que revertir — que es exactamente por qué no se agregó un estado.
        """
        if self.estado is not EstadoCobro.APROBADO:
            raise InvarianteViolada(MENSAJE_SOLO_PAGADOS_SE_REEMBOLSAN)
        pedido = redondear(monto)
        if pedido <= 0:
            raise EntradaInvalida(MENSAJE_MONTO_NO_POSITIVO)
        if pedido > self.monto:
            raise EntradaInvalida(MENSAJE_REEMBOLSO_EXCEDIDO)

        self.reembolso_solicitado_en = ahora
        self.updated_at = ahora
        return pedido

    def confirmar_reembolso(self, *, monto: Decimal, ahora: datetime) -> None:
        """MercadoPago confirmó (RN-04). Recién ahora el cobro cambia de estado."""
        self._transicionar(EstadoCobro.REEMBOLSADO)
        self.monto_reembolsado = redondear(monto)
        self.reembolso_solicitado_en = None
        self.updated_at = ahora

    def rechazar_reembolso(self, ahora: datetime) -> None:
        """MercadoPago dijo que no (RN-03). El cobro **mantiene** su estado `APROBADO`.

        No hay transición porque no hubo cambio de estado, y ahí está la elegancia de D27: la
        vuelta atrás no existe porque nunca se fue.
        """
        self.reembolso_solicitado_en = None
        self.updated_at = ahora

    @property
    def reembolso_en_proceso(self) -> bool:
        return self.reembolso_solicitado_en is not None

    # ------------------------------------------------------------------ consultas

    @property
    def esta_abierto(self) -> bool:
        """Sigue esperando plata: es lo que los dos barridos del épico buscan."""
        return self.estado in (EstadoCobro.PENDIENTE, EstadoCobro.VENCIDO)

    @property
    def recibe_recordatorios(self) -> bool:
        """HS-T3 RN-03. Un cobro aprobado o cancelado deja de recibirlos."""
        return self.esta_abierto

    def esta_vencido_a(self, ahora: datetime) -> bool:
        """Si ya pasó su vencimiento. Distinto de `estado is VENCIDO`, y a propósito.

        Esto es un hecho del calendario; el estado es lo que el barrido escribió. Entre los
        dos hay una ventana de minutos (D23), y quien necesite el hecho tiene que poder
        preguntarlo sin esperar al barrido.
        """
        return ahora >= self.vence_el

    def _exigir_cobrable(self) -> None:
        if not self.esta_abierto:
            raise InvarianteViolada(
                f"Un cobro en estado {self.estado.value} ya no admite un link de pago"
            )

    def _transicionar(self, destino: EstadoCobro) -> None:
        if destino not in TRANSICIONES_LEGALES[self.estado]:
            raise InvarianteViolada(f"Un cobro no pasa de {self.estado.value} a {destino.value}")
        self.estado = destino


__all__ = [
    "CENTAVOS",
    "LARGO_MINIMO_DE_MOTIVO",
    "MENSAJE_MONTO_NO_POSITIVO",
    "MENSAJE_MOTIVO_CORTO",
    "MENSAJE_PAGADO_NO_CANCELABLE",
    "MENSAJE_REEMBOLSO_EXCEDIDO",
    "MENSAJE_SIN_CONCEPTO",
    "MENSAJE_SOLO_PAGADOS_SE_REEMBOLSAN",
    "TRANSICIONES_LEGALES",
    "VIGENCIA_POR_DEFECTO",
    "Cobro",
    "EstadoCobro",
    "LinkDePago",
    "redondear",
]
