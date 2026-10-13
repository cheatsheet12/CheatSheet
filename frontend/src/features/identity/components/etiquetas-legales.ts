/**
 * How the two legal documents are named and dated on screen, in one place: the public pages,
 * the re-acceptance screen and the links all call them the same thing.
 */

import type { DocumentoLegal } from "../api/cliente";

export const TITULOS_LEGALES: Readonly<Record<DocumentoLegal, string>> = {
  TERMINOS: "Términos y Condiciones",
  PRIVACIDAD: "Política de Privacidad",
};

/** The public route of each text (HU-E1-03 RN-04, HU-E1-08 RN-06). */
export const RUTAS_LEGALES: Readonly<Record<DocumentoLegal, string>> = {
  TERMINOS: "/terminos",
  PRIVACIDAD: "/privacidad",
};

/** `2026-10-10` to `10/10/2026`, without going through `Date` and its time zone. */
export function fechaLegible(dia: string): string {
  const [anio, mes, diaDelMes] = dia.split("-");
  return `${diaDelMes}/${mes}/${anio}`;
}
