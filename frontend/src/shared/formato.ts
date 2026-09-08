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
    // `hour12: false` explícito, y por eso no alcanza con `timeStyle: "short"`: el ICU de
    // algunos entornos devuelve «9:00 p. m.» para `es-AR`, que no es como se escribe una
    // hora acá. Tres pantallas —agenda, conversaciones y auditoría— ya lo habían parcheado
    // por su cuenta; el arreglo va en el único lugar donde no hace falta repetirlo.
    //
    // Va junto a `timeStyle` y no como `hour`/`minute` sueltos: `dateStyle`/`timeStyle` no
    // se pueden combinar con los componentes individuales —`Intl` lo rechaza con
    // «Invalid option»—, pero `hour12` sí es compatible con ellos.
    timeStyle: "short",
    hour12: false,
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

/**
 * Sólo fecha, sin hora: `2026-09-01`. El resto de los valores llevan hora y zona.
 *
 * Se distinguen porque `Date` los interpreta distinto y el estándar lo manda: una cadena
 * de sólo fecha es **UTC**, una con hora sin zona es **local**. `new Date("2026-09-01")`
 * es entonces la medianoche UTC, que en Buenos Aires (UTC−3) todavía es el 31 de agosto a
 * las 21:00 — y la pantalla mostraba «31/8/26» para el primero de septiembre.
 */
const SOLO_FECHA = /^\d{4}-\d{2}-\d{2}$/;

function aFecha(iso: string | null): Date | null {
  if (iso === null || iso.trim() === "") {
    return null;
  }
  // Un día calendario no tiene instante: es el mismo día en cualquier zona. Se lo ancla al
  // mediodía UTC, que cae dentro del mismo día en todo el rango de UTC−11 a UTC+12, así
  // que ninguna zona lo corre de fecha.
  const crudo = iso.trim();
  const fecha = new Date(SOLO_FECHA.test(crudo) ? `${crudo}T12:00:00Z` : crudo);
  return Number.isNaN(fecha.getTime()) ? null : fecha;
}
