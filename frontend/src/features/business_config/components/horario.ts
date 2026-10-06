/**
 * Lo que la tarjeta de horario de atención calcula sin pintar nada: el estado editable, su
 * validación antes de guardar y la vuelta a la forma de la API.
 *
 * **La validación del backend manda** (el dominio la repite con los mismos textos): acá sólo
 * sirve para marcar el error antes de mandar y no dejar «Guardar» encendido con un horario que
 * el backend va a rechazar.
 */

import type { DiaDeAtencion } from "../api/atencion";

export const MENSAJE_CIERRE_ANTES_QUE_APERTURA =
  "La hora de cierre debe ser posterior a la de apertura.";
export const MENSAJE_FRANJAS_SUPERPUESTAS =
  "Las franjas de un mismo día no pueden superponerse ni tocarse.";
export const MENSAJE_FORMATO_DE_HORA = "El horario debe tener el formato HH:MM.";
export const MENSAJE_SIN_DIAS = "Indicá al menos un día con horario de atención.";

/** El fin del día: el `input type="time"` no lo admite, así que va con su propia casilla. */
export const MEDIANOCHE = "24:00";

export interface FilaDeFranja {
  readonly clave: string;
  readonly desde: string;
  readonly hasta: string;
}

export interface DiaEditable {
  /** Lunes 0. */
  readonly dia: number;
  readonly activo: boolean;
  readonly franjas: readonly FilaDeFranja[];
}

const HORA = /^(?:([01]\d|2[0-3]):[0-5]\d|24:00)$/;

let secuencia = 0;

export function nuevaFranja(desde = "09:00", hasta = "19:00"): FilaDeFranja {
  secuencia += 1;
  return { clave: `franja-${secuencia}`, desde, hasta };
}

/** Los valores del prototipo: lunes a viernes de 09:00 a 19:00, sábado de 09:00 a 14:00. */
export function diasDelPrototipo(): DiaEditable[] {
  return Array.from({ length: 7 }, (_, dia) => {
    if (dia <= 4) {
      return { dia, activo: true, franjas: [nuevaFranja("09:00", "19:00")] };
    }
    return dia === 5
      ? { dia, activo: true, franjas: [nuevaFranja("09:00", "14:00")] }
      : { dia, activo: false, franjas: [] };
  });
}

/** Siete días, con las franjas de los que la regla trae y apagados los demás. */
export function diasEditables(guardados: readonly DiaDeAtencion[]): DiaEditable[] {
  return Array.from({ length: 7 }, (_, dia) => {
    const guardado = guardados.find((uno) => uno.dia === dia);
    if (guardado === undefined) {
      return { dia, activo: false, franjas: [] };
    }
    return {
      dia,
      activo: true,
      franjas: guardado.franjas.map((uno) => nuevaFranja(uno.desde, uno.hasta)),
    };
  });
}

function ordenadas(franjas: readonly FilaDeFranja[]): FilaDeFranja[] {
  return [...franjas].sort((una, otra) => una.desde.localeCompare(otra.desde));
}

/** El error de un día (de los mismos textos que el dominio), o `null` si está bien o apagado. */
export function errorDelDia(dia: DiaEditable): string | null {
  if (!dia.activo) {
    return null;
  }
  if (dia.franjas.some((uno) => !HORA.test(uno.desde) || !HORA.test(uno.hasta))) {
    return MENSAJE_FORMATO_DE_HORA;
  }
  if (dia.franjas.some((uno) => uno.hasta <= uno.desde)) {
    return MENSAJE_CIERRE_ANTES_QUE_APERTURA;
  }
  const franjas = ordenadas(dia.franjas);
  for (let indice = 1; indice < franjas.length; indice += 1) {
    const anterior = franjas[indice - 1];
    const actual = franjas[indice];
    // `<=`: dos franjas que se tocan son una sola, y hay una única forma de escribirla.
    if (anterior !== undefined && actual !== undefined && actual.desde <= anterior.hasta) {
      return MENSAJE_FRANJAS_SUPERPUESTAS;
    }
  }
  return null;
}

export function hayAlgunDia(dias: readonly DiaEditable[]): boolean {
  return dias.some((uno) => uno.activo && uno.franjas.length > 0);
}

/** A la forma de la API: sólo los días con franjas, cada una ordenada por «desde». */
export function aDias(dias: readonly DiaEditable[]): DiaDeAtencion[] {
  return dias
    .filter((uno) => uno.activo && uno.franjas.length > 0)
    .map((uno) => ({
      dia: uno.dia,
      franjas: ordenadas(uno.franjas).map(({ desde, hasta }) => ({ desde, hasta })),
    }));
}

/** El día de hoy en Argentina (`AAAA-MM-DD`): una fecha sin atención es una fecha local. */
export function hoyEnArgentina(ahora: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Argentina/Buenos_Aires",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(ahora);
}
