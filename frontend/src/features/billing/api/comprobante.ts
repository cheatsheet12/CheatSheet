/**
 * What PAN-FAC-01, PAN-FAC-02 and PAN-FAC-03 call.
 *
 * **The amounts are strings from end to end.** They arrive as strings, they are sent as
 * strings, and nothing here parses one into a `number`. A JSON number becomes a JavaScript
 * float, which is the type the backend refuses anywhere near money — and it is wrong in the
 * fourth decimal, exactly where a centavo lives. The screen formats them for display and
 * never computes with them: what a customer owes is decided by the backend and by ARCA.
 *
 * **There is no `eliminar` and no `editar`.** A document with a CAE is a legal record: it
 * is reversed with a credit note, which is a different document. The backend grants no
 * DELETE, so a function here could only ever fail.
 */

import type { TipoComprobante } from "./puntoDeVenta";

export type EstadoComprobante =
  | "BORRADOR"
  | "VALIDADO"
  | "ENVIADO_A_ARCA"
  | "AUTORIZADO"
  | "RECHAZADO"
  | "ANULADO";

export interface ItemDeComprobante {
  readonly id: string;
  readonly descripcion: string;
  readonly cantidad: string;
  readonly precio_unitario: string;
  readonly alicuota_iva: string;
  readonly subtotal: string;
  readonly iva: string;
}

export interface Comprobante {
  readonly id: string;
  readonly tipo: TipoComprobante;
  readonly estado: EstadoComprobante;
  readonly numero: number | null;
  readonly punto_de_venta_id: string;
  readonly cliente_id: string;
  readonly receptor_nombre: string;
  readonly receptor_cuit: string;
  readonly receptor_condicion_iva: string;
  readonly cae: string | null;
  readonly cae_vence_el: string | null;
  readonly motivo_de_rechazo: string | null;
  readonly subtotal: string;
  readonly total_iva: string;
  readonly total: string;
  readonly saldo_pendiente: string;
  readonly fecha_emision: string | null;
  readonly created_at: string;
  readonly descargable: boolean;
  readonly items: readonly ItemDeComprobante[];
}

export interface ListadoDeComprobantes {
  readonly comprobantes: readonly Comprobante[];
}

export interface ReceptorValidado {
  readonly nombre: string;
  readonly cuit: string;
  readonly condicion_iva: string;
  /** RN-01: only the types this pair of VAT conditions allows. */
  readonly tipos_disponibles: readonly TipoComprobante[];
}

export interface ItemNuevo {
  readonly descripcion: string;
  readonly cantidad: string;
  readonly precio_unitario: string;
  readonly alicuota_iva: string;
}

export interface ComprobanteNuevo {
  readonly cliente_id: string;
  readonly punto_de_venta_id: string;
  readonly tipo: TipoComprobante;
  readonly receptor_cuit: string;
  readonly receptor_domicilio: string | null;
  readonly items: readonly ItemNuevo[];
}

export interface FiltrosDeComprobante {
  readonly desde?: string;
  readonly hasta?: string;
  readonly tipo?: string;
  readonly estado?: string;
}

/** HU-E5-01, word for word, for the empty state of PAN-FAC-01. */
export const MENSAJE_SIN_RESULTADOS = "No hay comprobantes para los filtros seleccionados.";
/** HU-E5-03, word for word. Shown before the request is even attempted. */
export const MENSAJE_SIN_ITEMS = "Debe agregar al menos un ítem para emitir el comprobante.";

/**
 * How each state is named on screen.
 *
 * **`ENVIADO_A_ARCA` reads «Pendiente»**, which is the word HU-E5-01 RN-02 uses for the
 * filter and the one the acceptance criterion expects after confirming an issue. The
 * domain name says what it is; this says what the user is waiting for.
 */
export const ETIQUETAS_DE_ESTADO: Readonly<Record<EstadoComprobante, string>> = {
  BORRADOR: "Borrador",
  VALIDADO: "Listo para emitir",
  ENVIADO_A_ARCA: "Pendiente",
  AUTORIZADO: "Autorizado",
  RECHAZADO: "Error",
  ANULADO: "Anulado",
};

/** The three rates the backend accepts, with the value it expects. */
export const ALICUOTAS: readonly { readonly valor: string; readonly etiqueta: string }[] = [
  { valor: "0.21", etiqueta: "IVA 21%" },
  { valor: "0.105", etiqueta: "IVA 10,5%" },
  { valor: "0.00", etiqueta: "IVA 0%" },
];

export class ErrorDeComprobante extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = "ErrorDeComprobante";
  }
}

interface CuerpoDeError {
  readonly error?: string;
  readonly detalle?: string;
}

async function fallar(respuesta: Response): Promise<never> {
  const cuerpo = (await respuesta.json().catch(() => ({}))) as CuerpoDeError;
  // `detalle` first: on a 422 the backend's sentence is either the story's own text or
  // ARCA's own words, and both are more specific than anything this file could invent.
  throw new ErrorDeComprobante(
    cuerpo.detalle ?? cuerpo.error ?? "No se pudo completar la operacion",
  );
}

function consultaDe(filtros: FiltrosDeComprobante): string {
  const parametros = new URLSearchParams();
  for (const [clave, valor] of Object.entries(filtros)) {
    if (valor !== undefined && valor !== "") {
      parametros.set(clave, valor);
    }
  }
  const texto = parametros.toString();
  return texto === "" ? "" : `?${texto}`;
}

export async function listarComprobantes(
  filtros: FiltrosDeComprobante = {},
): Promise<ListadoDeComprobantes> {
  const respuesta = await fetch(`/api/comprobantes${consultaDe(filtros)}`, {
    cache: "no-store",
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as ListadoDeComprobantes;
}

export async function verComprobante(comprobanteId: string): Promise<Comprobante> {
  const respuesta = await fetch(`/api/comprobantes/${comprobanteId}`, { cache: "no-store" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Comprobante;
}

/**
 * HU-E5-03 RN-02. The first step of PAN-FAC-03 and the one that gates the rest.
 *
 * The check digit is validated by the backend before it asks ARCA, which is what the story
 * means by «no consulta a ARCA»: this file does not duplicate that check, because a second
 * implementation of a modulo-11 is a second chance to disagree about which CUITs are real.
 */
export async function validarReceptor(cuit: string): Promise<ReceptorValidado> {
  const respuesta = await fetch(`/api/comprobantes/receptores/${encodeURIComponent(cuit)}`, {
    cache: "no-store",
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as ReceptorValidado;
}

/** Answers 202, not 201: the document exists and ARCA has not answered yet (RN-04). */
export async function emitirComprobante(datos: ComprobanteNuevo): Promise<Comprobante> {
  const respuesta = await fetch("/api/comprobantes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(datos),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Comprobante;
}

/**
 * `0001-00000123`, the way ARCA prints it on the document.
 *
 * A document without a number is a draft, and saying so beats printing `0001-00000000` —
 * which looks like a real number that happens to be zero.
 */
export function numeroFormateado(comprobante: Comprobante, puntoNumero: number | null): string {
  if (comprobante.numero === null) {
    return "Sin numerar";
  }
  const punto = puntoNumero === null ? "----" : String(puntoNumero).padStart(4, "0");
  return `${punto}-${String(comprobante.numero).padStart(8, "0")}`;
}

/** Which badge tone a state gets. `RECHAZADO` is the only one that is an error. */
export function tonoDeEstado(estado: EstadoComprobante): "ok" | "atencion" | "pendiente" | "error" {
  if (estado === "AUTORIZADO") {
    return "ok";
  }
  if (estado === "RECHAZADO") {
    return "error";
  }
  if (estado === "ENVIADO_A_ARCA") {
    return "atencion";
  }
  return "pendiente";
}

/** HU-E5-04. What PAN-FAC-04 preloads and the detail shows (RN-05). */
export interface Anulacion {
  readonly total_original: string;
  readonly total_anulado: string;
  /** The ceiling for the next credit note (RN-03), **against what is left**. */
  readonly disponible: string;
  readonly es_total: boolean;
  readonly es_parcial: boolean;
  readonly notas: readonly Comprobante[];
}

/** HU-E5-04, word for word. */
export const MENSAJE_MONTO_EXCEDIDO =
  "El monto de la nota de crédito no puede superar el del comprobante original.";
export const MENSAJE_SIN_ORIGEN = "Debe seleccionar el comprobante que desea anular.";

export async function verAnulacion(comprobanteId: string): Promise<Anulacion> {
  const respuesta = await fetch(`/api/comprobantes/${comprobanteId}/anulacion`, {
    cache: "no-store",
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Anulacion;
}

/**
 * Emit a credit note against one document.
 *
 * **No `tipo` and no receptor travel.** Both come from the original (RN-02), and sending
 * them would let a caller choose which kind of document reverses which — which ARCA
 * rejects. Only the lines being reversed go out.
 */
export async function emitirNotaDeCredito(
  comprobanteId: string,
  items: readonly ItemNuevo[],
): Promise<Comprobante> {
  const respuesta = await fetch(`/api/comprobantes/${comprobanteId}/notas-de-credito`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items }),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Comprobante;
}
