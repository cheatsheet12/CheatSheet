/**
 * Dates, times and numbers in the user's language and time zone (HU-E1-07 RN-03).
 *
 * **This is what `pref_idioma` actually governs.** The interface is not translated — the
 * system has one language, and standing up an i18n pipeline for a catalogue of one is
 * infrastructure with nobody on the other side. What the preference does change is real
 * and visible: whether a timestamp reads 14:30 or 2:30 PM, and whether it is shown in
 * Buenos Aires or in Ushuaia. That difference matters on a screen listing when an
 * invoice was issued.
 *
 * Everything here is pure and takes the preferences as arguments. A module-level
 * "current locale" would be shared mutable state, and the server renders for a different
 * user on every request.
 */

export interface PreferenciasDeFormato {
  readonly idioma: string;
  readonly zonaHoraria: string;
}

export const PREFERENCIAS_POR_DEFECTO: PreferenciasDeFormato = {
  idioma: "es-AR",
  zonaHoraria: "America/Argentina/Buenos_Aires",
};

/** An ISO-8601 instant, or `null` when there is nothing to show. */
export function formatearFechaHora(
  iso: string | null,
  preferencias: PreferenciasDeFormato = PREFERENCIAS_POR_DEFECTO,
): string {
  const fecha = aFecha(iso);
  if (fecha === null) {
    return "—";
  }
  return new Intl.DateTimeFormat(preferencias.idioma, {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: preferencias.zonaHoraria,
  }).format(fecha);
}

export function formatearFecha(
  iso: string | null,
  preferencias: PreferenciasDeFormato = PREFERENCIAS_POR_DEFECTO,
): string {
  const fecha = aFecha(iso);
  if (fecha === null) {
    return "—";
  }
  return new Intl.DateTimeFormat(preferencias.idioma, {
    dateStyle: "short",
    timeZone: preferencias.zonaHoraria,
  }).format(fecha);
}

/**
 * A decimal that arrived as a string.
 *
 * Money crosses the wire as text on purpose — a JSON number is a float, and CLAUDE.md §5
 * forbids those for amounts. Parsing it here, at the last moment before display, is the
 * only place a float is acceptable: nothing is computed from the result.
 */
export function formatearNumero(
  valor: string,
  preferencias: PreferenciasDeFormato = PREFERENCIAS_POR_DEFECTO,
  decimales = 2,
): string {
  const numero = Number(valor);
  if (!Number.isFinite(numero)) {
    return valor;
  }
  return new Intl.NumberFormat(preferencias.idioma, {
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
  }).format(numero);
}

function aFecha(iso: string | null): Date | null {
  if (iso === null || iso.trim() === "") {
    return null;
  }
  const fecha = new Date(iso);
  return Number.isNaN(fecha.getTime()) ? null : fecha;
}
