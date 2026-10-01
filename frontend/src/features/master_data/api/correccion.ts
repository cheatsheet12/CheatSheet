/**
 * What the «Formato de los datos existentes» section of PAN-DM-01 calls.
 *
 * Four operations, all for the Administrador, all mirroring `api/routers/correccion.py`.
 * The keys of the maps are the backend's enum values (`CLIENTE`, `COLISION_DE_CATEGORIA`…);
 * turning them into words is the component's job, not this module's.
 *
 * **The error keeps its HTTP status.** The three failures this screen distinguishes — 403
 * (not an Administrador), 409 (a correction is already running) and 422 (the run does not
 * exist) are told apart by status, and the backend's text is not written for the screen.
 */

export type EntidadCorregible = "CLIENTE" | "SERVICIO" | "CATEGORIA";

export type MotivoDeOmision =
  | "COLISION_DE_CATEGORIA"
  | "NOMBRE_INVALIDO"
  | "DURACION_FUERA_DE_REGLA";

export interface EjemploDeCorreccion {
  readonly antes: string;
  readonly despues: string;
}

export interface InformeDeCorreccion {
  readonly a_corregir: Readonly<Partial<Record<EntidadCorregible, number>>>;
  readonly omitidos: Readonly<Partial<Record<MotivoDeOmision, number>>>;
  readonly ejemplos: Readonly<Partial<Record<EntidadCorregible, readonly EjemploDeCorreccion[]>>>;
}

export interface ResultadoDeCorreccion {
  readonly corrida_id: string;
  readonly conteos: Readonly<Partial<Record<EntidadCorregible, number>>>;
}

export interface ResultadoDeRestauracion {
  readonly restaurados: number;
  readonly conservados: number;
}

export interface Corrida {
  readonly corrida_id: string;
  readonly creada_en: string;
  readonly cantidad: number;
}

export interface ListadoDeCorridas {
  readonly corridas: readonly Corrida[];
}

export class ErrorDeCorreccion extends Error {
  readonly estado: number;

  constructor(estado: number, mensaje: string) {
    super(mensaje);
    this.name = "ErrorDeCorreccion";
    this.estado = estado;
  }
}

async function pedir<T>(ruta: string, metodo: "GET" | "POST"): Promise<T> {
  const respuesta = await fetch(ruta, { method: metodo });
  const datos: unknown = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    const detalle = (datos as { detalle?: string }).detalle;
    throw new ErrorDeCorreccion(respuesta.status, detalle ?? "No se pudo completar la operacion");
  }
  return datos as T;
}

const BASE = "/api/datos-maestros/correccion";

/** The dry-run: counts and examples, nothing written. */
export async function informarCorreccion(): Promise<InformeDeCorreccion> {
  return pedir<InformeDeCorreccion>(`${BASE}/informe`, "GET");
}

export async function aplicarCorreccion(): Promise<ResultadoDeCorreccion> {
  return pedir<ResultadoDeCorreccion>(BASE, "POST");
}

export async function listarCorridas(): Promise<ListadoDeCorridas> {
  return pedir<ListadoDeCorridas>(`${BASE}/corridas`, "GET");
}

export async function restaurarCorreccion(corridaId: string): Promise<ResultadoDeRestauracion> {
  return pedir<ResultadoDeRestauracion>(`${BASE}/corridas/${corridaId}/restauracion`, "POST");
}
