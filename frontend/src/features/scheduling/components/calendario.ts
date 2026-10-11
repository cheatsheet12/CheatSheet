/**
 * Las cuentas de fechas de la agenda: el día de un turno, su hora, la semana que lo contiene
 * y cómo se reparten el ancho los turnos que se pisan.
 *
 * Todo puro y sin estado, para poder probarlo sin dibujar nada.
 *
 * **La zona es la de la agenda y es fija.** Un turno de las 22 de un martes es del martes para
 * quien lo atiende, aunque en UTC ya sea miércoles, y el navegador de quien mira puede estar en
 * otra zona. Por eso nada de acá usa `toISOString().slice(0, 10)` ni `new Date("AAAA-MM-DD")`
 * sobre un instante: el día se saca con `Intl` y la zona explícita. Los días calendario
 * (`AAAA-MM-DD`) sí se suman en UTC al mediodía, que nunca cae en otro día.
 */

import { PREFERENCIAS_POR_DEFECTO } from "@/shared";

import type { Turno } from "../api/turno";

export type VistaDeAgenda = "lista" | "semana" | "dia" | "mes";

const ZONA = PREFERENCIAS_POR_DEFECTO.zonaHoraria;
const IDIOMA = PREFERENCIAS_POR_DEFECTO.idioma;

/**
 * El desfase de la zona de la agenda (Argentina no tiene horario de verano).
 *
 * Se manda en el rango de la vista para que el backend lo lea como el comienzo del día de la
 * agenda y no como la medianoche de otra zona.
 */
const DESFASE = "-03:00";

export const MINUTOS_POR_DIA = 24 * 60;

function dosDigitos(numero: number): string {
  return String(numero).padStart(2, "0");
}

const FORMATO_DE_FECHA = new Intl.DateTimeFormat("en-US", {
  timeZone: ZONA,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

const FORMATO_DE_HORA = new Intl.DateTimeFormat("en-GB", {
  timeZone: ZONA,
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

function parte(partes: Intl.DateTimeFormatPart[], tipo: string): string {
  return partes.find((una) => una.type === tipo)?.value ?? "00";
}

/** El día (`AAAA-MM-DD`) de un instante, en la zona de la agenda. */
export function diaDe(iso: string): string {
  const partes = FORMATO_DE_FECHA.formatToParts(new Date(iso));
  return `${parte(partes, "year")}-${parte(partes, "month")}-${parte(partes, "day")}`;
}

/** Los minutos transcurridos desde la medianoche de la agenda, en la zona de la agenda. */
export function minutosDelDia(iso: string): number {
  const partes = FORMATO_DE_HORA.formatToParts(new Date(iso));
  return Number(parte(partes, "hour")) * 60 + Number(parte(partes, "minute"));
}

/** `HH:mm`, 24 horas, en la zona de la agenda. */
export function horaEnAgenda(iso: string): string {
  const minutos = minutosDelDia(iso);
  return `${dosDigitos(Math.floor(minutos / 60))}:${dosDigitos(minutos % 60)}`;
}

function aFecha(dia: string): Date {
  return new Date(`${dia}T12:00:00Z`);
}

export function sumarDias(dia: string, cantidad: number): string {
  const fecha = aFecha(dia);
  fecha.setUTCDate(fecha.getUTCDate() + cantidad);
  return `${fecha.getUTCFullYear()}-${dosDigitos(fecha.getUTCMonth() + 1)}-${dosDigitos(fecha.getUTCDate())}`;
}

/** 0 = lunes … 6 = domingo. */
function indiceDeSemana(dia: string): number {
  return (aFecha(dia).getUTCDay() + 6) % 7;
}

export function lunesDe(dia: string): string {
  return sumarDias(dia, -indiceDeSemana(dia));
}

export function semanaDe(dia: string): readonly string[] {
  const lunes = lunesDe(dia);
  return Array.from({ length: 7 }, (_, indice) => sumarDias(lunes, indice));
}

/**
 * El rango que pide una vista de calendario, con los mismos parámetros `desde`/`hasta` que usa
 * el filtro de fechas. `hasta` es exclusivo: el lunes siguiente no entra en la semana.
 */
export function rangoDeVista(
  vista: Exclude<VistaDeAgenda, "lista">,
  ancla: string,
): { readonly desde: string; readonly hasta: string } {
  if (vista === "mes") {
    // Las semanas completas que dibuja la grilla, con los días de los meses vecinos.
    const semanas = semanasDelMes(ancla);
    const ultima = semanas[semanas.length - 1] ?? [];
    return {
      desde: `${semanas[0]?.[0] ?? ancla}T00:00:00${DESFASE}`,
      hasta: `${sumarDias(ultima[6] ?? ancla, 1)}T00:00:00${DESFASE}`,
    };
  }
  const desde = vista === "semana" ? lunesDe(ancla) : ancla;
  const hasta = sumarDias(desde, vista === "semana" ? 7 : 1);
  return { desde: `${desde}T00:00:00${DESFASE}`, hasta: `${hasta}T00:00:00${DESFASE}` };
}

/** El primer día (`AAAA-MM-01`) del mes que contiene a `dia`. */
export function primeroDelMes(dia: string): string {
  return `${dia.slice(0, 7)}-01`;
}

/** Suma meses conservando el día; si el mes de destino es más corto cae en su último día. */
export function sumarMeses(dia: string, cantidad: number): string {
  const [anio = 0, mes = 1, numero = 1] = dia.split("-").map(Number);
  const total = anio * 12 + (mes - 1) + cantidad;
  const anioNuevo = Math.floor(total / 12);
  const mesNuevo = (total % 12) + 1;
  const ultimo = new Date(Date.UTC(anioNuevo, mesNuevo, 0)).getUTCDate();
  return `${anioNuevo}-${dosDigitos(mesNuevo)}-${dosDigitos(Math.min(numero, ultimo))}`;
}

/**
 * Las semanas (lunes a domingo) que cubren el mes de `ancla`: cinco o seis filas, con los
 * días de los meses vecinos que completan la primera y la última.
 */
export function semanasDelMes(ancla: string): readonly (readonly string[])[] {
  const primero = primeroDelMes(ancla);
  const ultimo = sumarDias(sumarMeses(primero, 1), -1);
  const semanas: (readonly string[])[] = [];
  for (let lunes = lunesDe(primero); lunes <= ultimo; lunes = sumarDias(lunes, 7)) {
    semanas.push(semanaDe(lunes));
  }
  return semanas;
}

function formatear(dia: string, opciones: Intl.DateTimeFormatOptions): string {
  return new Intl.DateTimeFormat(IDIOMA, { ...opciones, timeZone: "UTC" }).format(aFecha(dia));
}

/** «martes 6 de octubre». */
export function diaLargo(dia: string): string {
  // Armado a mano: según el ICU, `es-AR` escribe «martes, 6 de octubre» o «martes 6 de octubre».
  const nombreDia = formatear(dia, { weekday: "long" });
  return `${nombreDia} ${formatear(dia, { day: "numeric" })} de ${formatear(dia, { month: "long" })}`;
}

/** «Hoy · martes 6 de octubre», «Mañana · …», «Ayer · …» o sólo el día. */
export function encabezadoDeDia(dia: string, hoy: string): string {
  if (dia === hoy) {
    return `Hoy · ${diaLargo(dia)}`;
  }
  if (dia === sumarDias(hoy, 1)) {
    return `Mañana · ${diaLargo(dia)}`;
  }
  if (dia === sumarDias(hoy, -1)) {
    return `Ayer · ${diaLargo(dia)}`;
  }
  return diaLargo(dia);
}

/** «6 – 12 de octubre», «28 de sept. – 4 de oct.» o, en la vista día, «martes 6 de octubre». */
export function rangoLegible(vista: Exclude<VistaDeAgenda, "lista">, ancla: string): string {
  if (vista === "dia") {
    return diaLargo(ancla);
  }
  if (vista === "mes") {
    return `${formatear(ancla, { month: "long" })} de ${formatear(ancla, { year: "numeric" })}`;
  }
  const lunes = lunesDe(ancla);
  const domingo = sumarDias(lunes, 6);
  const mismoMes = lunes.slice(0, 7) === domingo.slice(0, 7);
  if (mismoMes) {
    const dia = formatear(lunes, { day: "numeric" });
    return `${dia} – ${formatear(domingo, { day: "numeric", month: "long" })}`;
  }
  const corto: Intl.DateTimeFormatOptions = { day: "numeric", month: "short" };
  return `${formatear(lunes, corto)} – ${formatear(domingo, corto)}`;
}

/** «lun», «mar»… para la cabecera de una columna. */
export function diaCorto(dia: string): string {
  return formatear(dia, { weekday: "short" }).replace(".", "");
}

export function numeroDeDia(dia: string): string {
  return formatear(dia, { day: "numeric" });
}

/** Los turnos agrupados por el día de su inicio, de más antiguo a más nuevo. */
export function agruparPorDia(
  turnos: readonly Turno[],
): readonly { readonly dia: string; readonly turnos: readonly Turno[] }[] {
  const grupos = new Map<string, Turno[]>();
  for (const turno of [...turnos].sort((a, b) => a.inicio.localeCompare(b.inicio))) {
    const dia = diaDe(turno.inicio);
    grupos.set(dia, [...(grupos.get(dia) ?? []), turno]);
  }
  return [...grupos.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([dia, delDia]) => ({ dia, turnos: delDia }));
}

/** «45 min», «1 h», «1 h 30 min». */
export function duracionLegible(minutos: number): string {
  if (minutos < 60) {
    return `${minutos} min`;
  }
  const horas = Math.floor(minutos / 60);
  const resto = minutos % 60;
  return resto === 0 ? `${horas} h` : `${horas} h ${resto} min`;
}

export interface Franja {
  readonly turno: Turno;
  /** Minutos desde la medianoche. */
  readonly inicio: number;
  readonly fin: number;
  /** El carril (0…) que ocupa dentro del grupo de turnos que se pisan. */
  readonly carril: number;
  /** Cuántos carriles tiene ese grupo: el ancho de cada franja es 1 / carriles. */
  readonly carriles: number;
}

/** Los minutos que ocupa un turno dentro de su día; un turno que cruza la medianoche se corta. */
export function intervaloDe(turno: Turno): { readonly inicio: number; readonly fin: number } {
  const inicio = minutosDelDia(turno.inicio);
  const cruza = diaDe(turno.fin) !== diaDe(turno.inicio);
  const fin = cruza ? MINUTOS_POR_DIA : minutosDelDia(turno.fin);
  // Un turno de duración cero o un fin anterior al inicio no debe desaparecer de la grilla.
  return { inicio, fin: Math.max(fin, inicio + 15) };
}

/**
 * Reparte los turnos de una columna en carriles: los que se pisan se dividen el ancho y los
 * que no, ocupan todo. Un grupo es una cadena de turnos que se tocan; dentro de él cada turno
 * va al primer carril libre.
 */
export function repartirEnCarriles(turnos: readonly Turno[]): readonly Franja[] {
  const ordenados = turnos
    .map((turno) => ({ turno, ...intervaloDe(turno) }))
    .sort((a, b) => a.inicio - b.inicio || b.fin - a.fin);

  const resultado: Franja[] = [];
  let grupo: { turno: Turno; inicio: number; fin: number; carril: number }[] = [];
  let finesDeCarril: number[] = [];
  let finDelGrupo = -1;

  const cerrar = (): void => {
    const carriles = finesDeCarril.length;
    for (const uno of grupo) {
      resultado.push({ ...uno, carriles });
    }
    grupo = [];
    finesDeCarril = [];
  };

  for (const actual of ordenados) {
    if (grupo.length > 0 && actual.inicio >= finDelGrupo) {
      cerrar();
    }
    let carril = finesDeCarril.findIndex((fin) => fin <= actual.inicio);
    if (carril === -1) {
      carril = finesDeCarril.length;
      finesDeCarril.push(actual.fin);
    } else {
      finesDeCarril[carril] = actual.fin;
    }
    finDelGrupo = grupo.length === 0 ? actual.fin : Math.max(finDelGrupo, actual.fin);
    grupo.push({ ...actual, carril });
  }
  cerrar();
  return resultado;
}

/**
 * Las horas que muestra la grilla: de 8 a 20 por defecto, ampliadas hacia afuera lo justo para
 * que ningún turno quede fuera de la vista.
 */
export function horasVisibles(turnos: readonly Turno[]): {
  readonly desde: number;
  readonly hasta: number;
} {
  let desde = 8;
  let hasta = 20;
  for (const turno of turnos) {
    const { inicio, fin } = intervaloDe(turno);
    desde = Math.min(desde, Math.floor(inicio / 60));
    hasta = Math.max(hasta, Math.ceil(fin / 60));
  }
  return { desde, hasta: Math.min(hasta, 24) };
}
