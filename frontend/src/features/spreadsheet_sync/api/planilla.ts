/**
 * What PAN-ING-01 calls.
 *
 * **The size and the extension are checked here too**, before a byte leaves the browser.
 * Not because the backend cannot be trusted to — it refuses the same two things and that
 * is the guarantee — but because uploading 30 MB in order to be told it was too big is a
 * minute of somebody's tethered connection spent on a foregone answer. The messages are
 * the ones HU-E3-03 writes, so the user reads the same sentence whichever side refused.
 */

/** Mirrors `ProveedorPlanilla` in the backend. `ARCHIVO` is decision D10 of the map. */
export type ProveedorPlanilla = "GOOGLE_SHEETS" | "EXCEL_ONLINE" | "ARCHIVO";
export type DireccionSync = "SOLO_LECTURA" | "LECTURA_Y_ESCRITURA";

export interface Vinculo {
  readonly id: string;
  readonly proveedor: ProveedorPlanilla;
  readonly direccion: DireccionSync;
  readonly hoja_empresa: string;
  readonly nombre_archivo: string | null;
  readonly tamano_bytes: number | null;
  readonly pausado: boolean;
  readonly motivo_de_pausa: string | null;
  readonly escribe_de_vuelta: boolean;
  readonly tiene_mapeo: boolean;
  readonly ultima_lectura: string | null;
  readonly created_at: string;
}

export interface ListadoDeVinculos {
  readonly vinculos: readonly Vinculo[];
}

/** HU-E3-03, word for word. Shared with the backend's `domain/valores.py`. */
export const EXTENSIONES_ACEPTADAS = [".xlsx", ".xls", ".csv"] as const;
export const LIMITE_TAMANO_MB = 25;
export const LIMITE_TAMANO_BYTES = LIMITE_TAMANO_MB * 1024 * 1024;
export const MENSAJE_FORMATO_NO_ACEPTADO = "Formato no aceptado. Use .xlsx, .xls o .csv.";
export const MENSAJE_ARCHIVO_DEMASIADO_GRANDE = `El archivo supera el límite de ${LIMITE_TAMANO_MB} MB.`;

/** How each provider is named on screen. The backend never sends a label. */
export const ETIQUETAS_DE_PROVEEDOR: Readonly<Record<ProveedorPlanilla, string>> = {
  GOOGLE_SHEETS: "Google Sheets",
  EXCEL_ONLINE: "Excel Online",
  ARCHIVO: "Archivo subido",
};

export class ErrorDePlanilla extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = "ErrorDePlanilla";
  }
}

interface CuerpoDeError {
  readonly error?: string;
  readonly detalle?: string;
}

async function fallar(respuesta: Response): Promise<never> {
  const cuerpo = (await respuesta.json().catch(() => ({}))) as CuerpoDeError;
  // `detalle` first: on a 422 the backend's sentence is the one the story wrote, and it
  // is more specific than anything this file could invent.
  throw new ErrorDePlanilla(cuerpo.detalle ?? cuerpo.error ?? "No se pudo completar la operacion");
}

export async function listarPlanillas(): Promise<ListadoDeVinculos> {
  const respuesta = await fetch("/api/planillas", { cache: "no-store" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as ListadoDeVinculos;
}

/** The two checks of HU-E3-03, run before the upload starts. See the module docstring. */
export function validarArchivo(archivo: File): void {
  const nombre = archivo.name.toLowerCase();
  if (!EXTENSIONES_ACEPTADAS.some((ext) => nombre.endsWith(ext))) {
    throw new ErrorDePlanilla(MENSAJE_FORMATO_NO_ACEPTADO);
  }
  if (archivo.size > LIMITE_TAMANO_BYTES) {
    throw new ErrorDePlanilla(MENSAJE_ARCHIVO_DEMASIADO_GRANDE);
  }
}

export async function subirPlanilla(archivo: File): Promise<Vinculo> {
  validarArchivo(archivo);

  const respuesta = await fetch(`/api/planillas/archivo?nombre=${encodeURIComponent(archivo.name)}`, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream" },
    body: archivo,
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Vinculo;
}

export async function iniciarVinculacionConGoogle(): Promise<string> {
  const respuesta = await fetch("/api/planillas/google/autorizacion", { method: "POST" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  const { url } = (await respuesta.json()) as { readonly url: string };
  return url;
}

export async function desvincularPlanilla(vinculoId: string): Promise<void> {
  const respuesta = await fetch(`/api/planillas/${vinculoId}`, { method: "DELETE" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
}
