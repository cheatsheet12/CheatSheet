/**
 * Lo que la tarjeta de un recurso muestra, calculado con los datos que la pantalla ya recibe.
 *
 * Son funciones puras y sin React: resumen el horario en una tira de siete días y en una franja
 * corta, y separan las excepciones próximas. No inventan nada: cada resultado sale de los
 * `patrones` y las `excepciones` del recurso tal como los devuelve la API.
 */

import { DIAS } from "../api/recurso";
import type { Excepcion, Patron } from "../api/recurso";

/** La inicial de cada día, de lunes a domingo. La «X» del miércoles es la convención rioplatense. */
export const INICIALES_DE_DIA: readonly string[] = ["L", "M", "X", "J", "V", "S", "D"];

export interface FilaDePatron extends Patron {
  readonly clave: string;
}

export function nuevaFila(dia = 0): FilaDePatron {
  return {
    clave: crypto.randomUUID(),
    dia_semana: dia,
    hora_inicio: "09:00:00",
    hora_fin: "18:00:00",
    duracion_slot_min: 30,
  };
}

/** «Lun», «Mié». La semana entera no entra en una etiqueta escrita con los nombres completos. */
export function abreviado(dia: number): string {
  return DIAS[dia]?.slice(0, 3) ?? "—";
}

/** Los días con al menos una franja, como conjunto de índices (0 = lunes). */
export function diasConHorario(patrones: readonly Patron[]): ReadonlySet<number> {
  return new Set(patrones.map((uno) => uno.dia_semana));
}

/**
 * Los días de un mismo horario, en una sola etiqueta: «Lun a Vie» o «Lun, Mié».
 *
 * Tres es el piso para el rango: con dos, «Lun a Mar» ocupa lo mismo que «Lun, Mar» y se lee peor.
 */
export function diasDe(dias: readonly number[]): string {
  const ordenados = [...dias].sort((uno, otro) => uno - otro);
  const primero = ordenados[0] ?? 0;
  const ultimo = ordenados[ordenados.length - 1] ?? 0;
  const corrido = ultimo - primero + 1 === ordenados.length;
  return corrido && ordenados.length >= 3
    ? `${abreviado(primero)} a ${abreviado(ultimo)}`
    : ordenados.map(abreviado).join(", ");
}

/** «09:00–18:00». */
export function franjaDe(patron: Patron): string {
  return `${patron.hora_inicio.slice(0, 5)}–${patron.hora_fin.slice(0, 5)}`;
}

export interface TramoDeHorario {
  readonly franja: string;
  readonly dias: string;
}

/**
 * Las franjas del recurso agrupadas por horario, ordenadas por el primer día en que rigen.
 *
 * Con un solo horario la tarjeta muestra la franja sola, porque los días ya están marcados en
 * la tira; con varios, cada tramo dice a qué días corresponde.
 */
export function tramosDeHorario(patrones: readonly Patron[]): readonly TramoDeHorario[] {
  const porFranja = new Map<string, number[]>();
  for (const patron of patrones) {
    const franja = franjaDe(patron);
    const dias = porFranja.get(franja);
    if (dias === undefined) {
      porFranja.set(franja, [patron.dia_semana]);
    } else if (!dias.includes(patron.dia_semana)) {
      dias.push(patron.dia_semana);
    }
  }
  return [...porFranja]
    .map(([franja, dias]) => ({ franja, dias, desde: Math.min(...dias) }))
    .sort((uno, otro) => uno.desde - otro.desde)
    .map(({ franja, dias }) => ({ franja, dias: diasDe(dias) }));
}

/** Las excepciones de hoy en adelante, de la más cercana a la más lejana. */
export function excepcionesProximas(
  excepciones: readonly Excepcion[],
  hoy: string,
): readonly Excepcion[] {
  return excepciones
    .filter((una) => una.fecha >= hoy)
    .sort((uno, otro) => uno.fecha.localeCompare(otro.fecha));
}

/** La fecha de hoy como `AAAA-MM-DD` en hora local, para comparar con `Excepcion.fecha`. */
export function hoyIso(ahora: Date = new Date()): string {
  const mes = String(ahora.getMonth() + 1).padStart(2, "0");
  const dia = String(ahora.getDate()).padStart(2, "0");
  return `${ahora.getFullYear()}-${mes}-${dia}`;
}
