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

import { PREFERENCIAS_POR_DEFECTO, formatearFecha } from "@/shared";
import type { PreferenciasDeFormato } from "@/shared";

export type TipoReporte = "FACTURACION" | "COBROS" | "OPERACIONES" | "RESUMEN_EJECUTIVO";
export type FormatoReporte = "PDF" | "CSV" | "XML";
export type EstadoReporte = "PENDIENTE" | "EN_CURSO" | "LISTO" | "FALLIDO";

export interface Metrica {
  readonly valor: string;
  readonly anterior: string;
  /** `null` cuando el período anterior fue cero. Ver el docstring del módulo. */
  readonly variacion: string | null;
}

/** Los cobros **creados** en el período que hoy están en un estado: cuántos y por cuánto. */
export interface CobrosDeUnEstado {
  readonly cantidad: number;
  readonly monto: string;
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
  /** Porcentaje ya redondeado por el backend, sobre lo creado en el período (RN-08). */
  readonly tasa_de_cobro: string;
  /** Semana ISO → lo cobrado neto de reembolsos. Puede ser negativo. */
  readonly cobrado_por_semana: Readonly<Record<string, string>>;
  /** Estado del cobro → cantidad y monto, en el orden del dominio. */
  readonly cobros_por_estado: Readonly<Record<string, CobrosDeUnEstado>>;
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

/** Cómo se llama cada estado **en pantalla**. `EN_CURSO` es un enum, no una palabra. */
export const ETIQUETAS_DE_ESTADO_DE_REPORTE: Readonly<Record<EstadoReporte, string>> = {
  PENDIENTE: "Pendiente",
  EN_CURSO: "En curso",
  LISTO: "Listo",
  FALLIDO: "Fallido",
};

/**
 * Cómo se llama en pantalla cada tipo de comprobante que el tablero agrupa.
 *
 * **No se importa el mapa de `billing` aunque diga casi lo mismo.** Las claves de `por_tipo`
 * llegan como texto libre —reportería agrupa por lo que encontró en la base, no por un enum
 * de esta feature—, así que el tipo de allá no describe lo que llega acá; y una feature que
 * importa a otra para leer una etiqueta ata dos módulos por el motivo más flojo que existe
 * (regla R5 de `CLAUDE.md` §2.1). Lo que sí se comparte es la redacción, que es de ARCA.
 */
export const ETIQUETAS_DE_TIPO_DE_COMPROBANTE: Readonly<Record<string, string>> = {
  FACTURA_A: "Factura A",
  FACTURA_B: "Factura B",
  FACTURA_C: "Factura C",
  NOTA_CREDITO_A: "Nota de crédito A",
  NOTA_CREDITO_B: "Nota de crédito B",
  NOTA_CREDITO_C: "Nota de crédito C",
  NOTA_DEBITO_A: "Nota de débito A",
  NOTA_DEBITO_B: "Nota de débito B",
  NOTA_DEBITO_C: "Nota de débito C",
};

/** `FACTURA_B` → `Factura B`. Las letras sueltas quedan en mayúscula: son de ARCA. */
function humanizarCodigo(clave: string): string {
  return clave
    .toLowerCase()
    .split("_")
    .map((palabra, indice) => {
      if (palabra.length === 1) {
        return palabra.toUpperCase();
      }
      return indice === 0 ? palabra.charAt(0).toUpperCase() + palabra.slice(1) : palabra;
    })
    .join(" ");
}

/**
 * El nombre legible de un tipo de comprobante, incluido el que este archivo todavía no conoce.
 *
 * El mapa cubre lo que hoy emite el sistema y el humanizador cubre lo que va a emitir mañana:
 * un `RECIBO_C` nuevo se lee «Recibo c», que es feo, pero infinitamente mejor que mostrarle
 * a alguien el identificador de una columna de la base en su tablero.
 */
export function nombreDeTipoDeComprobante(clave: string): string {
  return ETIQUETAS_DE_TIPO_DE_COMPROBANTE[clave] ?? humanizarCodigo(clave);
}

const MS_POR_DIA = 86_400_000;
const DIAS_POR_SEMANA = 7;
const SEMANA_ISO = /^(\d{4})-W(\d{1,2})$/;

/**
 * El lunes de una semana ISO-8601, en UTC.
 *
 * La norma ancla la semana 1 en la que contiene al 4 de enero; a partir del lunes de esa
 * semana, todo son saltos de siete días. **Toda la aritmética es en UTC a propósito**: hecha
 * con horas locales, la noche en que cambia el huso horario corre un día entero y la semana
 * pasa a empezar un domingo.
 */
function lunesDeSemanaIso(anio: number, semana: number): Date {
  const cuatroDeEnero = Date.UTC(anio, 0, 4);
  // `getUTCDay` devuelve 0 para el domingo; ISO lo cuenta como el séptimo día, no el primero.
  const diaDeLaSemana = new Date(cuatroDeEnero).getUTCDay() || DIAS_POR_SEMANA;
  const lunesDeLaSemana1 = cuatroDeEnero - (diaDeLaSemana - 1) * MS_POR_DIA;
  return new Date(lunesDeLaSemana1 + (semana - 1) * DIAS_POR_SEMANA * MS_POR_DIA);
}

interface SemanaResuelta {
  readonly lunes: Date;
  readonly domingo: Date;
}

function resolverSemana(clave: string): SemanaResuelta | null {
  const partes = SEMANA_ISO.exec(clave);
  if (partes === null) {
    return null;
  }
  const lunes = lunesDeSemanaIso(Number(partes[1]), Number(partes[2]));
  return { lunes, domingo: new Date(lunes.getTime() + (DIAS_POR_SEMANA - 1) * MS_POR_DIA) };
}

/**
 * Los dos extremos de la semana se formatean **en UTC**, y no en la zona del usuario.
 *
 * Una semana ISO es un rango de días del calendario, no un instante: no ocurre en ninguna
 * zona horaria. Pasarla por `America/Argentina/Buenos_Aires` le restaría tres horas a una
 * medianoche que no existe y devolvería el domingo anterior.
 */
function partesDeDia(fecha: Date, idioma: string, mes: "short" | "long" | undefined): string {
  return new Intl.DateTimeFormat(idioma, {
    day: "numeric",
    ...(mes === undefined ? {} : { month: mes }),
    timeZone: "UTC",
  }).format(fecha);
}

/** `2026-W37` → `7–13 sept`. Para el eje del gráfico, donde la frase larga no entra. */
export function etiquetaDeSemana(
  clave: string,
  preferencias: PreferenciasDeFormato = PREFERENCIAS_POR_DEFECTO,
): string {
  const semana = resolverSemana(clave);
  if (semana === null) {
    // Una clave que este archivo no sabe leer se muestra tal cual: fea, pero cierta.
    return clave;
  }
  const inicio = partesDeDia(semana.lunes, preferencias.idioma, undefined);
  return `${inicio}–${partesDeDia(semana.domingo, preferencias.idioma, "short")}`;
}

/** `2026-W37` → `Semana del 7 al 13 de septiembre`. */
export function nombreDeSemana(
  clave: string,
  preferencias: PreferenciasDeFormato = PREFERENCIAS_POR_DEFECTO,
): string {
  const semana = resolverSemana(clave);
  if (semana === null) {
    return clave;
  }
  const mismoMes = semana.lunes.getUTCMonth() === semana.domingo.getUTCMonth();
  const desde = partesDeDia(semana.lunes, preferencias.idioma, mismoMes ? undefined : "long");
  const hasta = partesDeDia(semana.domingo, preferencias.idioma, "long");
  return `Semana del ${desde} al ${hasta}`;
}

/**
 * Un día suelto del backend (`2026-09-01`), tal como se lee en el resto del panel.
 *
 * **El mediodía no es un capricho.** `new Date("2026-09-01")` es medianoche *UTC*, y en
 * Buenos Aires esa medianoche todavía es el 31 de agosto: el período de septiembre se
 * mostraría arrancando en agosto. Anclado al mediodía quedan doce horas de margen de cada
 * lado, así que el día del calendario sobrevive a cualquier zona que las preferencias elijan.
 */
export function textoDeDia(
  dia: string,
  preferencias: PreferenciasDeFormato = PREFERENCIAS_POR_DEFECTO,
): string {
  return formatearFecha(`${dia}T12:00:00Z`, preferencias);
}

/** `2026-09-01`, `2026-09-30` → `1/9/26 – 30/9/26`. */
export function textoDePeriodo(
  desde: string,
  hasta: string,
  preferencias: PreferenciasDeFormato = PREFERENCIAS_POR_DEFECTO,
): string {
  return `${textoDeDia(desde, preferencias)} – ${textoDeDia(hasta, preferencias)}`;
}

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
