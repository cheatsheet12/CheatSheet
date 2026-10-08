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
from uuid import UUID, uuid4

from cheatsheet.contexts.payments.application.pagos_sin_imputar import RegistrarPagoSinImputar
from cheatsheet.contexts.payments.application.ports import (
    PagoRecibido,
    PortPasarelaDePago,
    PortRepositorioCobro,
    PortSaldoDeComprobante,
)
from cheatsheet.contexts.payments.application.ports_de_pagos import PortRepositorioPagoSinImputar
from cheatsheet.contexts.payments.domain.cobro import Cobro, EstadoCobro
from cheatsheet.contexts.payments.domain.dinero import redondear
from cheatsheet.contexts.payments.domain.pago_sin_imputar import MotivoSinImputar
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.events import PublicadorDeEventos

logger = obtener_logger(__name__)

#: La única moneda en la que se crean los cobros (`currency_id` de la preferencia).
MONEDA_DE_COBRO = "ARS"


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
    #: Entró plata que **no se pudo imputar** (sin cobro, cobro ya pagado o monto distinto) y
    #: quedó registrada como `PagoSinImputar` con su alerta. Cuarto desenlace, con su propia
    #: bandera por lo mismo que los otros: la bitácora tiene que poder distinguirlo.
    sin_imputar: bool = False


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
        sin_imputar: PortRepositorioPagoSinImputar,
    ) -> None:
        self._cobros = cobros
        self._pasarela = pasarela
        self._saldos = saldos
        self._publicador = publicador
        self._sin_imputar = sin_imputar
        self._registro = RegistrarPagoSinImputar(pagos=sin_imputar, publicador=publicador)

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
        # **La misma línea para los pagos que no se pudieron imputar**: una segunda notificación
        # del mismo pago no llama a MercadoPago ni vuelve a avisar.
        if await self._sin_imputar.buscar_por_payment_id(payment_id) is not None:
            logger.info("webhook_repetido_sin_imputar", payment_id=payment_id)
            return ResultadoDeConfirmacion(aprobado=False, ya_procesado=True, sin_imputar=True)

        pago = await self._pasarela.consultar_pago(empresa_id=empresa_id, payment_id=payment_id)
        if not pago.esta_aprobado:
            # No es un error: `pending` e `in_process` llegan por este mismo webhook. Se
            # registra y se deja el cobro donde está, esperando la notificación buena.
            logger.info("webhook_pago_no_aprobado", payment_id=payment_id, estado=pago.estado)
            return ResultadoDeConfirmacion(aprobado=False)

        cobro = await self._encontrar(pago)
        if cobro is None:
            # Un pago **aprobado** al que no le encontramos cobro es plata que entró y no se
            # imputó a nada: se registra y se avisa, no se pierde en un log. (Los no aprobados
            # ya salieron arriba: solo el aprobado mueve plata.)
            return await self._registrar_sin_imputar(
                empresa_id, pago, MotivoSinImputar.SIN_COBRO, None, ahora
            )

        return await self._aprobar(empresa_id=empresa_id, cobro=cobro, pago=pago, ahora=ahora)

    async def _encontrar(self, pago: PagoRecibido) -> Cobro | None:
        """A qué cobro corresponde: primero por `external_reference`, después por preferencia.

        La referencia es el id del cobro, que la preferencia manda y MercadoPago propaga al
        pago; sobrevive a un link regenerado, que cambia la preferencia de la fila. Se busca
        bajo RLS: una referencia con el id de un cobro de **otra** empresa no se ve. La
        preferencia queda por compatibilidad (el pago de Checkout Pro no la trae, §20.17).

        **El cobro vuelve leído con `FOR UPDATE` por los dos caminos.** Dos webhooks con
        `payment_id` distinto sobre el mismo cobro abierto, sin bloqueo, lo aprobarían los dos
        (el segundo pisa `mp_payment_id` y el saldo baja dos veces, y el primer pago nunca queda
        registrado). Con el bloqueo el segundo espera, ve `APROBADO` y queda `COBRO_YA_PAGADO`.
        """
        cobro = await self._por_referencia(pago.referencia_externa)
        if cobro is not None or pago.preference_id is None:
            return cobro
        por_preferencia = await self._cobros.buscar_por_preference_id(pago.preference_id)
        if por_preferencia is None:
            return None
        # La búsqueda por preferencia no bloquea: se vuelve a leer la fila con bloqueo, que
        # además refresca el estado que otra transacción haya cambiado mientras tanto.
        return await self._cobros.buscar_para_actualizar(por_preferencia.id)

    async def _por_referencia(self, referencia: str | None) -> Cobro | None:
        if referencia is None:
            return None
        try:
            cobro_id = UUID(referencia)
        except ValueError:
            return None
        return await self._cobros.buscar_para_actualizar(cobro_id)

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
            # Un cobro ya pagado que recibe **otro** `payment_id`: o MercadoPago reprocesó con un
            # id distinto (a confirmar, `TODO.md` §20.19) o el cliente pagó dos veces. En los dos
            # casos entró plata y alguien tiene que verla, así que se registra y se avisa. La
            # tabla de transiciones no admite `APROBADO -> APROBADO`: esto lo vuelve una
            # respuesta y no un 500 que haría reintentar otra vez.
            return await self._registrar_sin_imputar(
                empresa_id, pago, MotivoSinImputar.COBRO_YA_PAGADO, cobro, ahora
            )

        if (pago.moneda is not None and pago.moneda != MONEDA_DE_COBRO) or (
            pago.monto is not None and redondear(pago.monto) != cobro.monto
        ):
            # El pago no cubre exactamente esta deuda (a confirmar con cuotas, §20.18) o es en
            # otra moneda (1210 USD no son 1210 ARS): no se aprueba sola. Si `transaction_amount`
            # o `currency_id` no vinieron no hay con qué contradecir al cobro.
            return await self._registrar_sin_imputar(
                empresa_id, pago, MotivoSinImputar.MONTO_DISTINTO, cobro, ahora
            )

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

    async def _registrar_sin_imputar(
        self,
        empresa_id: EmpresaId,
        pago: PagoRecibido,
        motivo: MotivoSinImputar,
        cobro: Cobro | None,
        ahora: datetime,
    ) -> ResultadoDeConfirmacion:
        """El pago queda registrado y alertado; el cobro, si lo hay, no se toca.

        Si otra notificación del mismo pago ganó la carrera por el índice único, el resultado es
        el de una repetida (`ya_procesado`) y no hay un segundo aviso.
        """
        nuevo = await self._registro.ejecutar(
            empresa_id=empresa_id,
            pago=pago,
            motivo=motivo,
            cobro_id=cobro.id if cobro else None,
            ahora=ahora,
        )
        return ResultadoDeConfirmacion(
            aprobado=False, ya_procesado=not nuevo, sin_imputar=True, cobro=cobro
        )

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
