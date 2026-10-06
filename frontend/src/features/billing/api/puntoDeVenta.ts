/**
 * What PAN-FAC-05 calls.
 *
 * **No `eliminar`.** The backend grants no `DELETE` on `punto_de_venta` — a point that
 * issued documents cannot be removed without orphaning them, and those documents carry a
 * CAE. HU-E5-05 RN-04 asks for deactivation instead, which is `cambiarEstado`.
 *
 * The two messages the story writes are constants here as well as in the backend, and for
 * a reason worth stating: this file does **not** use them to pre-validate. It shows what
 * the backend answered. They exist so the tests can assert the sentence the user reads is
 * the sentence the story wrote, and so a future reader sees which strings are load-bearing.
 */

/** Mirrors `TipoComprobante` in the backend, ARCA codes and all. */
export type TipoComprobante =
  | "FACTURA_A"
  | "FACTURA_B"
  | "FACTURA_C"
  | "NOTA_CREDITO_A"
  | "NOTA_CREDITO_B"
  | "NOTA_CREDITO_C";

export interface PuntoDeVenta {
  readonly id: string;
  readonly numero: number;
  readonly descripcion: string | null;
  readonly activo: boolean;
  /** `{tipo: ultimo_numero}`. Only the types that ever issued appear. */
  readonly numerador_por_tipo: Readonly<Partial<Record<TipoComprobante, number>>>;
  readonly created_at: string;
}

export interface ListadoDePuntosDeVenta {
  readonly puntos: readonly PuntoDeVenta[];
}

export interface DatosDePuntoDeVenta {
  readonly numero: number;
  readonly descripcion: string | null;
}

/** HU-E5-05, word for word. The backend sends these; nothing here composes them. */
export const MENSAJE_NO_HABILITADO = "El punto de venta no está habilitado en ARCA.";
export const MENSAJE_DUPLICADO = "Ya existe un punto de venta con ese número.";

/** How each document type is named on screen. The backend never sends a label. */
export const ETIQUETAS_DE_TIPO: Readonly<Record<TipoComprobante, string>> = {
  FACTURA_A: "Factura A",
  FACTURA_B: "Factura B",
  FACTURA_C: "Factura C",
  NOTA_CREDITO_A: "Nota de crédito A",
  NOTA_CREDITO_B: "Nota de crédito B",
  NOTA_CREDITO_C: "Nota de crédito C",
};

export class ErrorDePuntoDeVenta extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = "ErrorDePuntoDeVenta";
  }
}

interface CuerpoDeError {
  readonly error?: string;
  readonly detalle?: string;
}

async function fallar(respuesta: Response): Promise<never> {
  const cuerpo = (await respuesta.json().catch(() => ({}))) as CuerpoDeError;
  // `detalle` first: on a 422 the backend's sentence is the story's own text, and it is
  // more specific than anything this file could invent.
  throw new ErrorDePuntoDeVenta(
    cuerpo.detalle ?? cuerpo.error ?? "No se pudo completar la operacion",
  );
}

export async function listarPuntosDeVenta(): Promise<ListadoDePuntosDeVenta> {
  const respuesta = await fetch("/api/puntos-de-venta", { cache: "no-store" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as ListadoDePuntosDeVenta;
}

export async function registrarPuntoDeVenta(datos: DatosDePuntoDeVenta): Promise<PuntoDeVenta> {
  const respuesta = await fetch("/api/puntos-de-venta", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(datos),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as PuntoDeVenta;
}

/**
 * RN-04. Reactivating re-checks ARCA on the backend, so this can fail with
 * `MENSAJE_NO_HABILITADO` even for a point that was registered successfully months ago.
 */
export async function cambiarEstadoDePuntoDeVenta(
  puntoId: string,
  activo: boolean,
): Promise<PuntoDeVenta> {
  const respuesta = await fetch(`/api/puntos-de-venta/${puntoId}/estado`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ activo }),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as PuntoDeVenta;
}

/** The numbering, as one line. Empty when the point has not issued anything yet. */
export function resumenDeNumeracion(punto: PuntoDeVenta): string {
  const entradas = Object.entries(punto.numerador_por_tipo) as [TipoComprobante, number][];
  return entradas.map(([tipo, ultimo]) => `${ETIQUETAS_DE_TIPO[tipo]}: ${ultimo}`).join(" · ");
}

/**
 * The credit note that reverses this invoice (HU-E5-04 RN-02).
 *
 * Mirrors the backend's `TipoComprobante.nota_de_credito`, and it is duplicated here for
 * one reason only: the screen has to *name* the document it is about to emit before the
 * request exists. Which type is actually issued is still decided by the backend from the
 * original — this never travels.
 */
export function notaDeCreditoDe(tipo: TipoComprobante): TipoComprobante {
  return tipo.replace("FACTURA", "NOTA_CREDITO") as TipoComprobante;
}
