/**
 * What PAN-REP-02 and the accountant's page call (HU-E10-04, HU-E10-05, HU-E10-06).
 *
 * **La invitación no devuelve el enlace.** No es una omisión de esta capa: el enlace existe
 * una sola vez, en el correo que sale. Mostrárselo al administrador lo dejaría en el historial
 * del navegador y en cualquier log del camino, que es justo lo que el hash en la base evita.
 *
 * **La página del contador no manda cookie ni token.** Su credencial es el valor que viene en
 * la URL, y por eso estas dos funciones reciben ese valor como argumento: no hay sesión de la
 * que sacarlo.
 */

import { PREFERENCIAS_POR_DEFECTO } from "@/shared";
import type { PreferenciasDeFormato } from "@/shared";

import { nombreDeTipoDeComprobante } from "./reporte";
import type { Tablero } from "./reporte";

export type ContenidoDelPaquete =
  | "FACTURAS"
  | "NOTAS_DE_CREDITO"
  | "REPORTE_DE_COBROS"
  | "LOG_DE_OPERACIONES"
  | "RESUMEN_EJECUTIVO";

export interface EstadoDelContador {
  readonly email: string | null;
  readonly invitado: boolean;
  readonly vence: string | null;
  readonly accesos: number;
}

export interface ConfiguracionDelPaquete {
  readonly activo: boolean;
  readonly dia_de_envio: number;
  readonly formatos: readonly string[];
  readonly contenido: readonly ContenidoDelPaquete[];
  readonly email_contador: string | null;
  readonly proximo_envio: string | null;
  readonly contador: EstadoDelContador;
}

export interface ConfiguracionNueva {
  readonly dia_de_envio: number;
  readonly formatos: readonly string[];
  readonly contenido: readonly ContenidoDelPaquete[];
  readonly email_contador: string | null;
  readonly activo: boolean;
}

export interface Paquete {
  readonly id: string;
  readonly periodo: string;
  readonly anio: number;
  readonly mes: number;
  readonly totales_por_tipo: Readonly<Record<string, Readonly<Record<string, string>>>>;
  readonly disponible: boolean;
}

export interface ListadoDePaquetes {
  readonly paquetes: readonly Paquete[];
}

export interface AccesoDelContador {
  readonly vence: string;
  readonly tablero: Tablero;
  readonly paquetes: ListadoDePaquetes;
}

/** HU-E10-04, HU-E10-05 y HU-E10-06, palabra por palabra. */
export const MENSAJE_SIN_EMAIL =
  "Debe indicar el email del contador para activar el envío automático.";
export const MENSAJE_EMAIL_INVALIDO = "Ingrese un email válido.";
export const MENSAJE_ACCESO_NO_DISPONIBLE = "El acceso a este paquete ya no está disponible.";

/** Qué puede llevar el paquete, con el nombre que la historia le da a cada cosa. */
export const ETIQUETAS_DE_CONTENIDO: Readonly<Record<ContenidoDelPaquete, string>> = {
  FACTURAS: "Facturas",
  NOTAS_DE_CREDITO: "Notas de crédito",
  REPORTE_DE_COBROS: "Reporte de cobros",
  LOG_DE_OPERACIONES: "Log de operaciones",
  RESUMEN_EJECUTIVO: "Resumen ejecutivo",
};

export const CONTENIDOS: readonly ContenidoDelPaquete[] = [
  "FACTURAS",
  "NOTAS_DE_CREDITO",
  "REPORTE_DE_COBROS",
  "LOG_DE_OPERACIONES",
  "RESUMEN_EJECUTIVO",
];

/** Del 1 al 28: febrero existe, y un envío del 30 no saldría nunca en febrero. */
export const DIA_MAXIMO_DE_ENVIO = 28;

/**
 * `2026`, `8` → `Agosto 2026`.
 *
 * El mes y el año vienen ya separados en el `Paquete`, así que no hay nada que parsear: se
 * arma un `Date` en UTC sólo para que `Intl` ponga el nombre del mes en el idioma del usuario.
 * **El mes se formatea aparte del año** porque `{ month: "long", year: "numeric" }` en es-AR
 * devuelve «agosto de 2026», y el rótulo de una columna no lleva preposición.
 */
export function nombreDelPeriodo(
  anio: number,
  mes: number,
  preferencias: PreferenciasDeFormato = PREFERENCIAS_POR_DEFECTO,
): string {
  const fecha = new Date(Date.UTC(anio, mes - 1, 1));
  if (Number.isNaN(fecha.getTime())) {
    return `${mes}/${anio}`;
  }
  const nombre = new Intl.DateTimeFormat(preferencias.idioma, {
    month: "long",
    timeZone: "UTC",
  }).format(fecha);
  return `${nombre.charAt(0).toUpperCase()}${nombre.slice(1)} ${anio}`;
}

/**
 * Cómo se llama en pantalla cada clave de `totales_por_tipo`.
 *
 * Hoy el backend agrupa por contenido del paquete (`FACTURAS`, `NOTAS_DE_CREDITO`), pero el
 * campo es un `jsonb` de claves libres y nada impide que mañana agrupe por tipo de comprobante.
 * Se prueban los dos mapas y, si ninguno la conoce, se muestra legible igual: la alternativa
 * es que la pantalla escupa el identificador de un enum del backend.
 */
export function nombreDeClaveDePaquete(clave: string): string {
  return ETIQUETAS_DE_CONTENIDO[clave as ContenidoDelPaquete] ?? nombreDeTipoDeComprobante(clave);
}

export class ErrorDePaquete extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = "ErrorDePaquete";
  }
}

interface CuerpoDeError {
  readonly error?: string;
  readonly detalle?: string;
}

async function fallar(respuesta: Response): Promise<never> {
  const cuerpo = (await respuesta.json().catch(() => ({}))) as CuerpoDeError;
  throw new ErrorDePaquete(cuerpo.detalle ?? cuerpo.error ?? "No se pudo completar la operacion");
}

export async function verConfiguracion(): Promise<ConfiguracionDelPaquete> {
  const respuesta = await fetch("/api/reporteria/configuracion", { cache: "no-store" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as ConfiguracionDelPaquete;
}

export async function guardarConfiguracion(
  datos: ConfiguracionNueva,
): Promise<ConfiguracionDelPaquete> {
  const respuesta = await fetch("/api/reporteria/configuracion", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(datos),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as ConfiguracionDelPaquete;
}

export async function listarPaquetes(): Promise<ListadoDePaquetes> {
  const respuesta = await fetch("/api/reporteria/paquetes", { cache: "no-store" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as ListadoDePaquetes;
}

/** El «paquete de prueba» del cuarto criterio de HU-E10-04. Sin período: el mes cerrado. */
export async function generarPaquete(periodo?: {
  readonly anio: number;
  readonly mes: number;
}): Promise<Paquete> {
  const respuesta = await fetch("/api/reporteria/paquetes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(periodo ?? {}),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Paquete;
}

/** HU-E10-05. Devuelve el **estado**, no el enlace. Ver el docstring del módulo. */
export async function invitarContador(email: string): Promise<EstadoDelContador> {
  const respuesta = await fetch("/api/reporteria/contador", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as EstadoDelContador;
}

export async function revocarContador(): Promise<void> {
  const respuesta = await fetch("/api/reporteria/contador", { method: "DELETE" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
}

export function urlDePaquete(paqueteId: string): string {
  return `/api/reporteria/paquetes/${paqueteId}/archivo`;
}

/** HU-E10-06. **Sin sesión**: la credencial es el valor del enlace. */
export async function verAccesoDelContador(valor: string): Promise<AccesoDelContador> {
  const respuesta = await fetch(`/api/contador/${encodeURIComponent(valor)}`, {
    cache: "no-store",
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as AccesoDelContador;
}

export function urlDePaqueteDelContador(valor: string, paqueteId: string): string {
  return `/api/contador/${encodeURIComponent(valor)}/paquetes/${paqueteId}`;
}
