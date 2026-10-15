"""HS-T1 — confirmar un pago desde el webhook de MercadoPago.

**Es el código que más veces se ejecuta con datos que no controlamos**, y el que más barato
sale hacer bien. Tres reglas lo gobiernan y las tres son decisiones de este épico:

- **D20 — la idempotencia es el `payment_id`, no una clave nuestra.** MercadoPago manda la
  misma notificación varias veces por diseño y reintenta durante horas ante cualquier cosa que
  no sea 2xx. Una clave en Redis protege durante su TTL y deja de proteger justo cuando llega
  la notificación tardía, que es el caso a cubrir. Una columna con índice único protege
  siempre y sobrevive a un `FLUSHALL`.
- **D21 — se persiste el pago dentro del request.** Contestar 200 y encolar todo es más rápido
  y deja el pago perdido si el encolado falla. Un webhook que contestó 200 es un webhook cuyo
  pago está guardado: eso es lo que MercadoPago tiene derecho a asumir.
- **D22 — una firma inválida se registra y se descarta con 200.** Un 401 le pide a MercadoPago
  que reintente una notificación que nunca va a validar.

**El estado que MercadoPago manda no es «pagado» por defecto.** `pending`, `in_process` y
`authorized` llegan por el mismo webhook que `approved`, y tratarlas como pago sería dar por
saldada una deuda que todavía puede rechazarse.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from cheatsheet.contexts.payments.application.ports import (
    PagoRecibido,
    PortPasarelaDePago,
    PortRepositorioCobro,
    PortSaldoDeComprobante,
)
from cheatsheet.contexts.payments.domain.cobro import Cobro, EstadoCobro
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.events import PublicadorDeEventos

logger = obtener_logger(__name__)


@dataclass(frozen=True, slots=True)
class ResultadoDeConfirmacion:
    """Qué hizo el webhook, para que el router sepa qué registrar.

    `ya_procesado` es distinto de `aprobado`: los dos terminan en 200 y sólo uno cambió algo.
    Sin esa distinción, la bitácora no podría mostrar cuántas veces MercadoPago reintentó — y
    esa cuenta es lo primero que se mira cuando un pago «no entró».
    """

    aprobado: bool
    ya_procesado: bool = False
    #: `None` cuando la notificación no correspondía a ningún cobro nuestro. Pasa: MercadoPago
    #: manda eventos de la cuenta entera, y una empresa puede cobrar por fuera del sistema.
    cobro: Cobro | None = None
    #: Entró plata por el link de un cobro **cancelado**. Ni `aprobado` ni `ya_procesado`: es
    #: un tercer desenlace, y tiene su propia bandera por lo mismo que `ya_procesado` tiene la
    #: suya — sin ella la bitácora no podría distinguir el caso que hay que mirar hoy.
    huerfano: bool = False

    @property
    def recien_aprobado(self) -> bool:
        """Este request fue el que aprobó el cobro: la única vez que corresponde avisar (RN-01).

        Ni lo repetido (`ya_procesado`), ni el pago sobre un cobro cancelado (`huerfano`), ni lo
        que MercadoPago todavía no aprobó. Es lo que vuelve idempotente el aviso: solo la
        transacción que ganó el índice único de `payment_id` llega a ser `recien_aprobado`.
        """
        return (
            self.aprobado and not self.ya_procesado and not self.huerfano and self.cobro is not None
        )


class ConfirmarPago:
    """Procesa una notificación ya autenticada. **Idempotente por construcción.**

    La firma se valida antes, en el borde (HS-T1 RN-01): una notificación que no valida no
    llega hasta acá. Ponerla adentro habría mezclado «es de MercadoPago» con «qué dice», que
    son dos preguntas con dos respuestas distintas ante un fallo.
    """

    def __init__(
        self,
        *,
        cobros: PortRepositorioCobro,
        pasarela: PortPasarelaDePago,
        saldos: PortSaldoDeComprobante,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._cobros = cobros
        self._pasarela = pasarela
        self._saldos = saldos
        self._publicador = publicador

    async def ejecutar(
        self, *, empresa_id: EmpresaId, payment_id: str, ahora: datetime
    ) -> ResultadoDeConfirmacion:
        # **Primera línea de la idempotencia (D20).** Antes de preguntarle nada a MercadoPago:
        # si ya procesamos este pago, no hay nada que hacer y no hace falta una llamada de red
        # para descubrirlo.
        ya = await self._cobros.buscar_por_payment_id(payment_id)
        if ya is not None:
            logger.info("webhook_repetido", payment_id=payment_id, cobro_id=str(ya.id))
            return ResultadoDeConfirmacion(aprobado=True, ya_procesado=True, cobro=ya)

        pago = await self._pasarela.consultar_pago(empresa_id=empresa_id, payment_id=payment_id)
        if not pago.esta_aprobado:
            # No es un error: `pending` e `in_process` llegan por este mismo webhook. Se
            # registra y se deja el cobro donde está, esperando la notificación buena.
            logger.info("webhook_pago_no_aprobado", payment_id=payment_id, estado=pago.estado)
            return ResultadoDeConfirmacion(aprobado=False)

        cobro = await self._encontrar(empresa_id, pago)
        if cobro is None:
            # MercadoPago manda eventos de la cuenta entera, y una empresa puede cobrar por
            # fuera del sistema. No es un error nuestro y no debe parecerlo.
            logger.info("webhook_sin_cobro_asociado", payment_id=payment_id)
            return ResultadoDeConfirmacion(aprobado=False)

        return await self._aprobar(empresa_id=empresa_id, cobro=cobro, pago=pago, ahora=ahora)

    async def _encontrar(self, empresa_id: EmpresaId, pago: PagoRecibido) -> Cobro | None:
        """A qué cobro corresponde: por `external_reference`, y si no, por la preferencia.

        Un pago de Checkout Pro casi nunca trae `preference_id`; `external_reference` sí, y es
        el id del cobro porque lo cargamos así al crear el link. Buscarlo dentro de la sesión
        de la empresa de la URL (RLS) es lo que impide que una referencia ajena encuentre algo;
        comparar la empresa es la segunda línea.
        """
        if pago.cobro_id is not None:
            cobro = await self._cobros.buscar_por_id(pago.cobro_id)
            if cobro is not None and cobro.empresa_id == empresa_id:
                return cobro
        if pago.preference_id is None:
            return None
        return await self._cobros.buscar_por_preference_id(pago.preference_id)

    async def _aprobar(
        self, *, empresa_id: EmpresaId, cobro: Cobro, pago: PagoRecibido, ahora: datetime
    ) -> ResultadoDeConfirmacion:
        if cobro.estado is EstadoCobro.CANCELADO:
            # Plata que entró por un link que debería estar muerto. **No es idempotencia**, y
            # tratarla como tal --que es lo que este código hacía-- dejaba el pago sin dueño,
            # sin bitácora y sin aviso, para que apareciera conciliando el extracto.
            return await self._registrar_huerfano(
                empresa_id=empresa_id, cobro=cobro, pago=pago, ahora=ahora
            )

        if not cobro.esta_abierto:
            # **Segunda línea de la idempotencia.** Un cobro ya aprobado por otra notificación
            # que llegó con otro `payment_id` -- raro, pero MercadoPago reintenta con ids
            # distintos cuando reprocesa. La tabla de transiciones lo rechazaría; esto lo
            # convierte en una respuesta y no en un 500 que haría reintentar otra vez.
            logger.info("webhook_sobre_cobro_cerrado", cobro_id=str(cobro.id))
            return ResultadoDeConfirmacion(aprobado=True, ya_procesado=True, cobro=cobro)

        # El link queda desactivado por el estado (`tiene_link_activo`), sin borrar la
        # preferencia: es lo que ata una notificación tardía a esta fila, y sin ella el
        # webhook siguiente diría «no es de esta empresa» sobre un cobro que sí lo es.
        # `fecha_aprobacion` es cuándo pagó el cliente (D91). Si MercadoPago no la informó o
        # no es plausible, el dominio usa `ahora` y marca la fecha como aproximada: un dato
        # ilegible nunca rompe el webhook.
        cobro.aprobar(payment_id=pago.payment_id, ahora=ahora, fecha_pago=pago.fecha_aprobacion)
        await self._cobros.guardar(cobro)

        # HS-T1 RN-03. Dentro de la misma transacción que la aprobación: un saldo que baja en
        # otra transacción es un saldo que puede no bajar. **Decisión D26**: es acá y en
        # ningún otro lado donde el comprobante se entera.
        if cobro.comprobante_id is not None:
            await self._saldos.registrar_cobro(cobro.comprobante_id, cobro.monto)

        # RN-05: iniciador Sistema. `usuario_id` nulo es lo que HS-T5 usa para eso.
        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                usuario_id=None,
                modulo=Modulo.PAYMENTS,
                accion="confirmar_pago",
                entidad_afectada=f"Cobro:{cobro.id}",
                resultado=Resultado.COMPLETADO,
            )
        )
        logger.info("pago_confirmado", cobro_id=str(cobro.id), payment_id=pago.payment_id)
        return ResultadoDeConfirmacion(aprobado=True, cobro=cobro)

    async def _registrar_huerfano(
        self, *, empresa_id: EmpresaId, cobro: Cobro, pago: PagoRecibido, ahora: datetime
    ) -> ResultadoDeConfirmacion:
        """Un pago entró por el link de un cobro cancelado (HU-E6-04 RN-03).

        Tres cosas pasan, y las tres importan:

        - **El cobro no cambia de estado.** Alguien lo dio de baja con un motivo escrito;
          resucitarlo con un webhook contradiría esa decisión, y `CANCELADO → APROBADO` no
          está en la tabla de transiciones justamente por eso.
        - **El `payment_id` queda atado a esta fila.** Es lo que vuelve idempotente la
          notificación repetida —`buscar_por_payment_id` la corta antes de llegar acá— y lo
          que le da al administrador por dónde empezar a buscar la plata.
        - **El saldo del comprobante no se toca.** Esa plata no está imputada a nada, y bajarle
          el saldo a un comprobante por un pago que nadie aceptó sería mentir en el balance del
          épico 9 (D26).

        El evento va con `Resultado.ERROR` a propósito: `NotificarPorEventos` lo convierte en
        una notificación de severidad alta, que es la única forma de que alguien se entere hoy
        y no cuando concilie el extracto.
        """
        cobro.registrar_pago_huerfano(payment_id=pago.payment_id, ahora=ahora)
        await self._cobros.guardar(cobro)

        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                # Iniciador Sistema, como el resto de lo que hace el webhook (RN-05).
                usuario_id=None,
                modulo=Modulo.PAYMENTS,
                accion="pago_sobre_cobro_cancelado",
                entidad_afectada=f"Cobro:{cobro.id}",
                resultado=Resultado.ERROR,
            )
        )
        logger.warning(
            "pago_sobre_cobro_cancelado",
            cobro_id=str(cobro.id),
            payment_id=pago.payment_id,
        )
        return ResultadoDeConfirmacion(aprobado=False, huerfano=True, cobro=cobro)


class RegistrarWebhookRechazado:
    """HS-T1 RN-01 — el intento queda registrado aunque la firma no valide (D22).

    Se registra **y se contesta 200**. Un 401 le diría a MercadoPago «reintentá», y
    reintentaría durante horas una notificación que nunca va a validar, llenando la bitácora
    de intentos idénticos. Una firma inválida no es un error transitorio.
    """

    def __init__(self, publicador: PublicadorDeEventos) -> None:
        self._publicador = publicador

    async def ejecutar(self, *, empresa_id: EmpresaId, motivo: str, ahora: datetime) -> None:
        logger.warning("webhook_rechazado", motivo=motivo)
        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                usuario_id=None,
                modulo=Modulo.PAYMENTS,
                accion="webhook_rechazado",
                entidad_afectada="Webhook:mercadopago",
                resultado=Resultado.ERROR,
            )
        )


__all__ = ["ConfirmarPago", "RegistrarWebhookRechazado", "ResultadoDeConfirmacion"]
