/**
 * What PAN-COB-01, PAN-COB-02 and PAN-COB-03 call.
 *
 * **The amounts are strings from end to end.** They arrive as strings and are sent as
 * strings, and nothing here parses one into a `number`. A JSON number becomes a JavaScript
 * float, which is the type the backend refuses anywhere near money — and it is wrong in the
 * fourth decimal, exactly where a centavo lives.
 *
 * **There is no `eliminar`.** A paid charge is money that came in: it is refunded. A pending
 * one is cancelled, which keeps the reason and the trail HU-E6-04 RN-04 asks for. The backend
 * grants no DELETE, so a function here could only ever fail.
 */

import type { Recordatorio } from "./recordatorio";
import type { OrigenDeReembolso, Reembolso } from "./reembolso";

export type EstadoCobro =
  | "PENDIENTE"
  | "APROBADO"
  | "VENCIDO"
  | "CANCELADO"
  | "REEMBOLSADO_PARCIAL"
  | "REEMBOLSADO";

/**
 * Por dónde entró la plata (ADR-0010). Un conjunto cerrado y **propio**: el vocabulario de
 * MercadoPago (tarjeta, dinero en cuenta) no llega hasta acá.
 */
export type MedioDePago = "LINK_MERCADOPAGO" | "TRANSFERENCIA";

export interface Cobro {
  readonly id: string;
  readonly cliente_id: string;
  readonly comprobante_id: string | null;
  readonly turno_id: string | null;
  readonly monto: string;
  /** El acumulado de reembolsos: `0.00` mientras no hubo ninguno. */
  readonly monto_reembolsado: string;
  readonly descripcion: string;
  readonly estado: EstadoCobro;
  readonly url_de_pago: string | null;
  readonly tiene_link_activo: boolean;
  readonly vence_el: string;
  /** Cuándo pagó el cliente (D91), en UTC. `null` mientras no se pagó. */
  readonly fecha_pago: string | null;
  /** `true` cuando `fecha_pago` es una estimación y no la fecha que informó el medio. */
  readonly fecha_pago_aproximada: boolean;
  readonly medio_de_pago: MedioDePago;
  /** Solo lo tienen las transferencias (HU-E6-02 RN-05); un pago por link lo deja en `null`. */
  readonly numero_de_operacion: string | null;
  /** HU-E6-05: la pantalla muestra «Reembolso en proceso» a partir de esto (D27). */
  readonly reembolso_en_proceso: boolean;
  /** Cuánto se pidió, mientras el reembolso está en vuelo. */
  readonly reembolso_en_proceso_monto: string | null;
  /**
   * HU-E6-04: entró plata por el link de un cobro cancelado.
   *
   * El backend ya avisó al administrador con una notificación de severidad alta; esto es
   * lo que hace que la pantalla a la que ese aviso lo manda muestre algo.
   */
  readonly tiene_pago_huerfano: boolean;
  readonly motivo_de_cancelacion: string | null;
  readonly created_at: string;
}

export interface DetalleDeCobro extends Cobro {
  /** HU-E6-02 criterio 1: el detalle muestra los datos del cliente, no solo su id. */
  readonly cliente_nombre: string;
  /** CUIT formateado para mostrar («20-22222222-3»); `null` si el cliente no tiene. */
  readonly cliente_cuit: string | null;
  readonly recordatorios: readonly Recordatorio[];
  /** Del más viejo al más nuevo; las correcciones son filas negativas visibles. */
  readonly reembolsos: readonly Reembolso[];
}

export interface MetricasDeCobros {
  readonly cobrado: string;
  readonly pendiente: string;
  readonly en_mora: string;
  readonly tasa_de_cobro: string;
}

export interface ListadoDeCobros {
  readonly cobros: readonly Cobro[];
  readonly metricas: MetricasDeCobros;
}

export interface CobroNuevo {
  readonly cliente_id: string;
  readonly monto: string;
  readonly descripcion: string;
  readonly comprobante_id?: string | null;
}

/** Lo que pide «Registrar reembolso» (HU-E6-05 RN-07). `fecha` es un día (`YYYY-MM-DD`). */
export interface ReembolsoManualNuevo {
  readonly monto: string;
  readonly fecha: string;
  readonly referencia: string;
  readonly motivo: string;
}

export interface FiltrosDeCobro {
  readonly desde?: string;
  readonly hasta?: string;
  readonly estado?: string;
}

/** HU-E6-01 y HU-E6-03, palabra por palabra. */
export const MENSAJE_SIN_RESULTADOS = "No hay cobros para los filtros seleccionados.";
export const MENSAJE_SIN_CONCEPTO = "Debe ingresar un concepto para el cobro.";
export const MENSAJE_MONTO_NO_POSITIVO = "El monto debe ser mayor a cero.";
export const MENSAJE_MOTIVO_CORTO = "El motivo debe tener al menos 10 caracteres.";
export const MENSAJE_LINK_COPIADO = "Link copiado al portapapeles.";
export const MENSAJE_LINK_REGENERADO =
  "Se generó un nuevo link de pago; el anterior quedó invalidado.";
export const MENSAJE_MP_CAIDO = "No se pudo generar el link de pago. Intente nuevamente.";

/**
 * HU-E6-04. Lo que PAN-COB-02 dice cuando entró plata por un link ya cancelado.
 *
 * No lo escribe una historia —la historia no contempla el caso— y por eso dice qué hacer y
 * no sólo qué pasó: el administrador llega acá desde una notificación y necesita el paso
 * siguiente, que está en MercadoPago y no en esta pantalla.
 */
export const MENSAJE_PAGO_HUERFANO =
  "Entró un pago por el link de este cobro después de cancelarlo. El dinero está en la cuenta de MercadoPago y no fue imputado a ninguna deuda. Revisalo y, si corresponde, devolvelo desde MercadoPago.";

/** HU-E6-04 RN-02. Lo valida el backend; acá sólo decide si el botón está gris. */
export const LARGO_MINIMO_DE_MOTIVO = 10;

/**
 * Cómo se llama cada estado **en pantalla**.
 *
 * Las historias son explícitas en que no coinciden con los del dominio: `APROBADO` se muestra
 * «Pagado» y `VENCIDO` se muestra «En mora». El dominio es la fuente de verdad; esto es
 * presentación, y por eso vive de este lado.
 */
export const ETIQUETAS_DE_ESTADO: Readonly<Record<EstadoCobro, string>> = {
  PENDIENTE: "Pendiente",
  APROBADO: "Pagado",
  VENCIDO: "En mora",
  CANCELADO: "Cancelado",
  REEMBOLSADO_PARCIAL: "Reembolsado parcialmente",
  REEMBOLSADO: "Reembolsado",
};

/** Cómo se llama cada medio de pago **en pantalla**. */
export const ETIQUETAS_DE_MEDIO: Readonly<Record<MedioDePago, string>> = {
  LINK_MERCADOPAGO: "Link de MercadoPago",
  TRANSFERENCIA: "Transferencia",
};

/** Cómo se llama cada origen de reembolso **en pantalla**. */
export const ETIQUETAS_DE_ORIGEN: Readonly<Record<OrigenDeReembolso, string>> = {
  API_MERCADOPAGO: "MercadoPago",
  MANUAL: "Manual",
};

/**
 * HU-E6-05 RN-09. El reembolso sube el saldo del comprobante pero **no** emite la nota de
 * crédito: solo se avisa que corresponde y se ofrece el camino.
 */
export const MENSAJE_NOTA_DE_CREDITO =
  "Este cobro está asociado a un comprobante. Corresponde emitir una nota de crédito por lo reembolsado: el sistema no la emite solo.";

/** El código con que el backend rechaza una clave de pedido ya usada con otros datos (ADR-0013). */
export const CODIGO_CLAVE_REUSADA = "ClaveDeIdempotenciaReusada";

export class ErrorDeCobro extends Error {
  /** El código del error del backend, si lo trajo: lo que permite a la pantalla ofrecer una salida. */
  readonly codigo: string | undefined;

  constructor(mensaje: string, codigo?: string) {
    super(mensaje);
    this.name = "ErrorDeCobro";
    this.codigo = codigo;
  }
}

interface CuerpoDeError {
  readonly error?: string;
  readonly detalle?: string;
}

async function fallar(respuesta: Response): Promise<never> {
  const cuerpo = (await respuesta.json().catch(() => ({}))) as CuerpoDeError;
  // `detalle` primero: en un 422 la frase del backend es la que escribió la historia, y es
  // más específica que cualquier cosa que este archivo pudiera inventar.
  throw new ErrorDeCobro(
    cuerpo.detalle ?? cuerpo.error ?? "No se pudo completar la operacion",
    cuerpo.error,
  );
}

function consultaDe(filtros: FiltrosDeCobro): string {
  const parametros = new URLSearchParams();
  for (const [clave, valor] of Object.entries(filtros)) {
    if (valor !== undefined && valor !== "") {
      parametros.set(clave, valor);
    }
  }
  const texto = parametros.toString();
  return texto === "" ? "" : `?${texto}`;
}

export async function listarCobros(filtros: FiltrosDeCobro = {}): Promise<ListadoDeCobros> {
  const respuesta = await fetch(`/api/cobros${consultaDe(filtros)}`, { cache: "no-store" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as ListadoDeCobros;
}

export async function verCobro(cobroId: string): Promise<DetalleDeCobro> {
  const respuesta = await fetch(`/api/cobros/${cobroId}`, { cache: "no-store" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as DetalleDeCobro;
}

/**
 * **La clave identifica el pedido, no el cobro** (ADR-0013): el formulario la genera una vez y
 * la manda en cada envío o reintento, y el backend contesta el cobro ya creado si la repite.
 */
export async function generarCobro(datos: CobroNuevo, clave: string): Promise<Cobro> {
  const respuesta = await fetch("/api/cobros", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Idempotency-Key": clave },
    body: JSON.stringify(datos),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Cobro;
}

/** El último criterio de HU-E6-03: invalida el anterior y activa el nuevo. */
export async function regenerarLink(cobroId: string): Promise<Cobro> {
  const respuesta = await fetch(`/api/cobros/${cobroId}/link`, { method: "POST" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Cobro;
}

export async function cancelarCobro(cobroId: string, motivo: string): Promise<Cobro> {
  const respuesta = await fetch(`/api/cobros/${cobroId}/cancelacion`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ motivo }),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Cobro;
}

/** HU-E6-05. **Sólo el Administrador** (RN-05); el backend lo refuerza. */
export async function reembolsarCobro(cobroId: string, monto: string): Promise<Cobro> {
  const respuesta = await fetch(`/api/cobros/${cobroId}/reembolso`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ monto }),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Cobro;
}

/**
 * «Actualizar estado» (HU-E6-05): destraba un reembolso que quedó en proceso.
 *
 * **Sólo el Administrador.** Con el id de MercadoPago consulta; sin id reenvía el pedido con la
 * misma clave de idempotencia, así que MercadoPago deduplica en vez de devolver dos veces.
 * Apretarlo sin nada en vuelo no hace nada.
 */
export async function actualizarReembolso(cobroId: string): Promise<Cobro> {
  const respuesta = await fetch(`/api/cobros/${cobroId}/reembolso/actualizacion`, {
    method: "POST",
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Cobro;
}

/**
 * «Registrar reembolso» (HU-E6-05 RN-07): la devolución de una transferencia, declarada a mano.
 *
 * El monto viaja como texto y la fecha como día (`YYYY-MM-DD`): el backend la guarda a las 12:00
 * de Argentina. La referencia se omite si quedó vacía.
 */
export async function registrarReembolso(
  cobroId: string,
  datos: ReembolsoManualNuevo,
): Promise<Cobro> {
  const referencia = datos.referencia.trim();
  const respuesta = await fetch(`/api/cobros/${cobroId}/reembolsos`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      monto: datos.monto,
      fecha: datos.fecha,
      ...(referencia === "" ? {} : { referencia }),
      motivo: datos.motivo,
    }),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Cobro;
}

/** HU-E6-05 RN-08: anula la fila entera con una fila negativa. Exige un motivo. */
export async function corregirReembolso(
  cobroId: string,
  reembolsoId: string,
  motivo: string,
): Promise<Cobro> {
  const respuesta = await fetch(`/api/cobros/${cobroId}/reembolsos/${reembolsoId}/correccion`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ motivo }),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Cobro;
}

/**
 * Los centavos de un monto en texto, **sin `Number()`**: `12500.10` es `1250010`.
 *
 * Un entero exacto (hasta cien millones de pesos son 10^10 centavos, muy por debajo de 2^53) y
 * no un float: restar `0.10` de `1000.00` con floats no da `999.90`.
 */
export function centavosDe(monto: string): number {
  const [entera = "0", decimales = ""] = monto.split(".");
  return (
    Number.parseInt(entera, 10) * 100 + Number.parseInt(decimales.padEnd(2, "0").slice(0, 2), 10)
  );
}

/** Cuánto falta devolver de un cobro (`monto - monto_reembolsado`), en texto de dos decimales. */
export function pendienteDeReembolso(cobro: Pick<Cobro, "monto" | "monto_reembolsado">): string {
  const centavos = centavosDe(cobro.monto) - centavosDe(cobro.monto_reembolsado);
  const entera = Math.trunc(centavos / 100);
  const resto = String(centavos % 100).padStart(2, "0");
  return `${entera}.${resto}`;
}

/** Si el cobro ya devolvió algo (el acumulado es mayor que cero). */
export function tieneReembolsos(cobro: Pick<Cobro, "monto_reembolsado">): boolean {
  return centavosDe(cobro.monto_reembolsado) > 0;
}

/**
 * Copia el link al portapapeles (HU-E6-02 RN-03).
 *
 * `navigator.clipboard` no existe fuera de un contexto seguro, y en ese caso **se dice** en
 * vez de fallar en silencio: alguien que apretó «copiar» y no ve nada asume que copió.
 */
export async function copiarLink(url: string): Promise<boolean> {
  if (typeof navigator === "undefined" || navigator.clipboard === undefined) {
    return false;
  }
  try {
    await navigator.clipboard.writeText(url);
    return true;
  } catch {
    return false;
  }
}

/** Qué tono de badge le toca a cada estado. */
export function tonoDeEstado(estado: EstadoCobro): "ok" | "atencion" | "pendiente" | "error" {
  if (estado === "APROBADO") {
    return "ok";
  }
  if (estado === "VENCIDO") {
    return "error";
  }
  // Un reembolso parcial es plata que cambió de lugar y todavía se puede seguir devolviendo:
  // pide un vistazo, a diferencia del total, que ya es un cierre.
  if (estado === "PENDIENTE" || estado === "REEMBOLSADO_PARCIAL") {
    return "atencion";
  }
  return "pendiente";
}
