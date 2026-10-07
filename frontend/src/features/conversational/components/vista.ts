/**
 * Lo que la bandeja y el hilo calculan sólo para **mostrarse**: tono estable de un avatar,
 * hora relativa y agrupación de mensajes por día. Nada de esto toca el dominio.
 */

import type { Mensaje } from "../api/conversacion";

/** Cantidad de tonos que define `pantallas-agente.css` (`.cv-tono-0` … `.cv-tono-5`). */
export const CANTIDAD_DE_TONOS = 6;

/** Un hash simple y estable: el mismo cliente tiene siempre el mismo color. */
export function tonoDe(clave: string): number {
  let hash = 0;
  for (const letra of clave) {
    hash = (hash * 31 + (letra.codePointAt(0) ?? 0)) % 100003;
  }
  return hash % CANTIDAD_DE_TONOS;
}

const UN_MINUTO = 60_000;
const UNA_HORA = 60 * UN_MINUTO;
const UN_DIA = 24 * UNA_HORA;

function inicioDelDia(fecha: Date): number {
  return new Date(fecha.getFullYear(), fecha.getMonth(), fecha.getDate()).getTime();
}

/**
 * «ahora», «hace 12 min», «hace 3 h», «ayer» o «8 sep». Una bandeja se lee por lo que pasó
 * hoy; lo más viejo se dice con la fecha corta.
 */
export function horaRelativa(iso: string | null, ahora: Date = new Date()): string {
  if (iso === null || iso.trim() === "") {
    return "—";
  }
  const momento = new Date(iso);
  if (Number.isNaN(momento.getTime())) {
    return "—";
  }
  const diferencia = ahora.getTime() - momento.getTime();
  if (diferencia < UN_MINUTO) {
    return "ahora";
  }
  if (diferencia < UNA_HORA) {
    return `hace ${Math.floor(diferencia / UN_MINUTO)} min`;
  }
  const dias = Math.round((inicioDelDia(ahora) - inicioDelDia(momento)) / UN_DIA);
  if (dias <= 0) {
    return `hace ${Math.floor(diferencia / UNA_HORA)} h`;
  }
  if (dias === 1) {
    return "ayer";
  }
  return momento.toLocaleDateString("es-AR", { day: "numeric", month: "short" }).replace(".", "");
}

/** El rótulo del separador de día: «Hoy», «Ayer» o «8 de septiembre». */
export function rotuloDeDia(iso: string, ahora: Date = new Date()): string {
  const momento = new Date(iso);
  if (Number.isNaN(momento.getTime())) {
    return "—";
  }
  const dias = Math.round((inicioDelDia(ahora) - inicioDelDia(momento)) / UN_DIA);
  if (dias === 0) {
    return "Hoy";
  }
  if (dias === 1) {
    return "Ayer";
  }
  return momento.toLocaleDateString("es-AR", { day: "numeric", month: "long" });
}

export interface GrupoDeDia {
  readonly clave: string;
  readonly rotulo: string;
  readonly mensajes: readonly Mensaje[];
}

function claveDeDia(iso: string): string {
  const momento = new Date(iso);
  if (Number.isNaN(momento.getTime())) {
    return "sin-fecha";
  }
  return `${momento.getFullYear()}-${momento.getMonth() + 1}-${momento.getDate()}`;
}

/** Agrupa mensajes consecutivos del mismo día, conservando el orden en que llegaron. */
export function agruparPorDia(
  mensajes: readonly Mensaje[],
  ahora: Date = new Date(),
): readonly GrupoDeDia[] {
  const grupos: { clave: string; rotulo: string; mensajes: Mensaje[] }[] = [];
  for (const mensaje of mensajes) {
    const clave = claveDeDia(mensaje.momento);
    const ultimo = grupos[grupos.length - 1];
    if (ultimo !== undefined && ultimo.clave === clave) {
      ultimo.mensajes.push(mensaje);
    } else {
      grupos.push({ clave, rotulo: rotuloDeDia(mensaje.momento, ahora), mensajes: [mensaje] });
    }
  }
  return grupos;
}
