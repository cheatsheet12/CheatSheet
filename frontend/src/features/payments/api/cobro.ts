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

export type EstadoCobro = "PENDIENTE" | "APROBADO" | "VENCIDO" | "CANCELADO" | "REEMBOLSADO";

export interface Recordatorio {
  readonly id: string;
  readonly paso: number;
  readonly canal: string;
  readonly enviado_en: string | null;
  readonly estado_entrega: string | null;
}

export interface Cobro {
  readonly id: string;
  readonly cliente_id: string;
  readonly comprobante_id: string | null;
  readonly turno_id: string | null;
  readonly monto: string;
  readonly monto_reembolsado: string | null;
  readonly descripcion: string;
  readonly estado: EstadoCobro;
  readonly url_de_pago: string | null;
  readonly tiene_link_activo: boolean;
  readonly vence_el: string;
  readonly pagado_en: string | null;
  /** HU-E6-05: la pantalla muestra «Reembolso en proceso» a partir de esto (D27). */
  readonly reembolso_en_proceso: boolean;
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
  readonly recordatorios: readonly Recordatorio[];
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
  REEMBOLSADO: "Reembolsado",
};

export class ErrorDeCobro extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = "ErrorDeCobro";
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
  throw new ErrorDeCobro(cuerpo.detalle ?? cuerpo.error ?? "No se pudo completar la operacion");
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

export async function generarCobro(datos: CobroNuevo): Promise<Cobro> {
  const respuesta = await fetch("/api/cobros", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
  if (estado === "PENDIENTE") {
    return "atencion";
  }
  return "pendiente";
}
