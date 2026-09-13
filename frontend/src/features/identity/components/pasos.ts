/**
 * Los tres pasos del onboarding, en un solo lugar.
 *
 * Estaban duplicados en cada pantalla, y un stepper que dice «Empresa» en un paso y
 * «Datos de empresa» en el siguiente es peor que no tener stepper: quien lo lee cree que
 * son dos cosas distintas.
 *
 * Los nombres son los del prototipo (`docs/aidlc/inputs/prototipos/onboarding.html`),
 * acortados a lo que entra en el punto del stepper sin partirse en dos líneas.
 */

import type { Paso } from "@/shared";

export const PASOS_DEL_ONBOARDING: readonly Paso[] = [
  { numero: 1, nombre: "Cuenta" },
  { numero: 2, nombre: "Empresa" },
  { numero: 3, nombre: "Integraciones" },
];

/** Cuánto del flujo quedó atrás al estar en un paso, para la barra de progreso. */
export function avanceDelPaso(paso: number): string {
  return `${Math.round((paso / PASOS_DEL_ONBOARDING.length) * 100)}%`;
}
