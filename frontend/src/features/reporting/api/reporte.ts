/**
 * What PAN-REP-01 calls: the dashboard, the preview and the report files (HU-E10-01 … 03).
 *
 * **Every amount is a string, end to end.** They arrive as strings and are never parsed into
 * a `number`: a JSON number is a JavaScript float, which is wrong in the fourth decimal —
 * exactly where a centavo lives — and it is the type the backend refuses anywhere near money.
 * The screen formats from the exact string.
 *
 * **`variacion` may be `null`, and that is not the same as zero.** «Creció 0%» and «no hay con
 * qué comparar» are different statements about somebody's business; the screen draws a dash
 * for the second one.
 *
 * **There is no `eliminar`.** The history of HU-E10-03 is the answer to «qué le mandé a mi
 * contador y cuándo»; the backend grants no DELETE, so a function here could only ever fail.
 */

export type TipoReporte = "FACTURACION" | "COBROS" | "OPERACIONES" | "RESUMEN_EJECUTIVO";
export type FormatoReporte = "PDF" | "CSV" | "XML";
export type EstadoReporte = "PENDIENTE" | "EN_CURSO" | "LISTO" | "FALLIDO";

export interface Metrica {
  readonly valor: string;
  readonly anterior: string;
  /** `null` cuando el período anterior fue cero. Ver el docstring del módulo. */
  readonly variacion: string | null;
}

export interface Tablero {
  readonly desde: string;
  readonly hasta: string;
  readonly facturado: Metrica;
  readonly cobrado: Metrica;
  readonly turnos: Metrica;
  readonly operaciones: Metrica;
  readonly por_tipo: Readonly<Record<string, string>>;
  readonly por_semana: Readonly<Record<string, string>>;
  readonly pendiente: string;
  readonly en_mora: string;
  readonly sin_actividad: boolean;
}

export interface Previsualizacion {
  readonly tipo: TipoReporte;
  readonly desde: string;
  readonly hasta: string;
  readonly cantidad: number;
  readonly total: string;
  readonly hay_datos: boolean;
}

export interface Reporte {
  readonly id: string;
  readonly tipo: TipoReporte;
  readonly formato: FormatoReporte;
  readonly desde: string;
  readonly hasta: string;
  readonly estado: EstadoReporte;
  readonly descargable: boolean;
}

export interface ListadoDeReportes {
  readonly reportes: readonly Reporte[];
}

export interface RangoDePeriodo {
  readonly desde?: string;
  readonly hasta?: string;
}

/** HU-E10-01 y HU-E10-03, palabra por palabra. */
export const MENSAJE_SIN_ACTIVIDAD = "No hay actividad registrada para este período.";
export const MENSAJE_SIN_DATOS = "No hay datos para generar el reporte en el período seleccionado.";

/** Cómo se llama cada tipo **en pantalla**. El valor que viaja es el del dominio. */
export const ETIQUETAS_DE_TIPO: Readonly<Record<TipoReporte, string>> = {
  FACTURACION: "Facturación",
  COBROS: "Cobros",
  OPERACIONES: "Operaciones",
  RESUMEN_EJECUTIVO: "Resumen ejecutivo",
};

/**
 * Qué formatos tiene sentido pedir para cada tipo.
 *
 * **Es la misma tabla que el backend, y está duplicada a propósito.** Del otro lado es la
 * regla —un `Reporte` con un formato que su tipo no admite no se construye—; de este lado es
 * lo que evita ofrecer una opción que va a terminar en un 422. Duplicar la regla sería malo;
 * duplicar la *lista* para no ofrecer lo imposible es lo que hace que la pantalla no mienta.
 */
export const FORMATOS_POR_TIPO: Readonly<Record<TipoReporte, readonly FormatoReporte[]>> = {
  FACTURACION: ["CSV", "XML"],
  COBROS: ["CSV"],
  OPERACIONES: ["CSV"],
  RESUMEN_EJECUTIVO: ["PDF"],
};

export class ErrorDeReporte extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = "ErrorDeReporte";
  }
}

interface CuerpoDeError {
  readonly error?: string;
  readonly detalle?: string;
}

async function fallar(respuesta: Response): Promise<never> {
  const cuerpo = (await respuesta.json().catch(() => ({}))) as CuerpoDeError;
  // `detalle` primero: en un 422 la frase del backend es la que escribió la historia.
  throw new ErrorDeReporte(cuerpo.detalle ?? cuerpo.error ?? "No se pudo completar la operacion");
}

function consultaDe(rango: RangoDePeriodo, extras: Record<string, string> = {}): string {
  const parametros = new URLSearchParams(extras);
  for (const [clave, valor] of Object.entries(rango)) {
    if (valor !== undefined && valor !== "") {
      parametros.set(clave, valor);
    }
  }
  const texto = parametros.toString();
  return texto === "" ? "" : `?${texto}`;
}

export async function verTablero(rango: RangoDePeriodo = {}): Promise<Tablero> {
  const respuesta = await fetch(`/api/reporteria/tablero${consultaDe(rango)}`, {
    cache: "no-store",
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Tablero;
}

/** HU-E10-02. **No genera nada**: se puede llamar cuantas veces haga falta. */
export async function previsualizar(
  tipo: TipoReporte,
  rango: RangoDePeriodo = {},
): Promise<Previsualizacion> {
  const respuesta = await fetch(`/api/reporteria/previsualizacion${consultaDe(rango, { tipo })}`, {
    cache: "no-store",
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Previsualizacion;
}

export async function listarReportes(): Promise<ListadoDeReportes> {
  const respuesta = await fetch("/api/reporteria/reportes", { cache: "no-store" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as ListadoDeReportes;
}

export async function generarReporte(
  tipo: TipoReporte,
  formato: FormatoReporte,
  rango: RangoDePeriodo = {},
): Promise<Reporte> {
  const respuesta = await fetch(`/api/reporteria/reportes${consultaDe(rango)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tipo, formato }),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Reporte;
}

/**
 * A dónde apunta el botón de descarga.
 *
 * Una URL y no un `fetch` que arme un `blob`: el navegador ya sabe descargar, y armar el
 * archivo en memoria para volver a soltarlo agrega un camino donde un archivo grande puede
 * fallar sin decir por qué.
 */
export function urlDeReporte(reporteId: string): string {
  return `/api/reporteria/reportes/${reporteId}/archivo`;
}
