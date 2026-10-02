/**
 * What PAN-AGE-01 and PAN-AGE-02 call (HU-E7-01, HU-E7-02, HU-E7-03, HU-E7-06).
 *
 * **No hay `eliminar`.** Un turno se cancela: queda en la agenda con su estado, que es lo que
 * hace auditable la ocupación de un recurso. El backend no otorga el permiso, así que una
 * función acá sólo podría fallar.
 *
 * **`reservar` puede fallar aunque el horario figurara libre.** El selector muestra lo que
 * está tomado en el momento de la consulta; quien decide es la restricción de exclusión de
 * PostgreSQL (decisión D28). Por eso el mensaje del backend se muestra tal cual: es el que
 * dice que alguien se adelantó.
 */

import { PREFERENCIAS_POR_DEFECTO } from "@/shared";

export type EstadoTurno = "RESERVADO" | "CONFIRMADO" | "CANCELADO" | "COMPLETADO" | "NO_SHOW";

export interface Turno {
  readonly id: string;
  readonly cliente_id: string;
  readonly servicio_id: string;
  readonly recurso_id: string;
  readonly cobro_id: string | null;
  readonly inicio: string;
  readonly duracion_min: number;
  readonly fin: string;
  readonly estado: EstadoTurno;
  readonly canal_reserva: string;
  /** HU-E7-03 RN-01: la pantalla ofrece marcar asistencia sólo cuando esto es `true`. */
  readonly ya_transcurrio: boolean;
  /** HU-E7-03 RN-02: un turno completado habilita emitir el comprobante del servicio. */
  readonly habilita_facturacion: boolean;
}

export interface ListadoDeTurnos {
  readonly turnos: readonly Turno[];
}

export interface Horario {
  readonly inicio: string;
  readonly ocupado: boolean;
}

export interface Disponibilidad {
  readonly fecha: string;
  readonly horarios: readonly Horario[];
}

export interface TurnoNuevo {
  readonly cliente_id: string;
  readonly servicio_id: string;
  readonly recurso_id: string;
  readonly inicio: string;
  /**
   * La carga a posteriori (HU-E7-06 RN-07), sólo del Administrador. Siempre explícita: el
   * backend nunca la infiere de un inicio pasado, y sin ella un inicio pasado se rechaza.
   */
  readonly a_posteriori?: boolean;
}

export interface FiltrosDeAgenda {
  readonly recurso_id?: string;
  readonly desde?: string;
  readonly hasta?: string;
  readonly estado?: string;
}

/**
 * Lo mínimo que la agenda necesita de algo que se nombra: su id y cómo se llama.
 *
 * Un `Turno` viaja con `cliente_id` y `servicio_id`, no con los nombres. La fila los muestra
 * porque un UUID en una agenda no le dice nada a quien la mira, y quien resuelve el nombre es
 * la página del servidor. Esta forma se declara acá —y no se importa de `master_data`— para
 * que la agenda no dependa de la definición completa de un cliente: de un cliente sólo usa el
 * nombre, y pedir el tipo entero ataría esta pantalla a cada campo que se le agregue allá.
 */
export interface Nombrado {
  readonly id: string;
  readonly nombre: string;
}

/** HU-E7-01, HU-E7-02, HU-E7-03 y HU-E7-06, palabra por palabra. */
export const MENSAJE_SIN_TURNOS = "No hay turnos para el período seleccionado.";
export const MENSAJE_HORARIO_OCUPADO = "El horario seleccionado no está disponible.";
export const MENSAJE_NO_TRANSCURRIO = "El turno aún no transcurrió.";
/** HU-E7-06 RN-06 y HU-E7-02 RN-06. El backend los manda tal cual; acá se nombran para los tests. */
export const MENSAJE_TURNO_EN_EL_PASADO = "No se puede agendar un turno en un horario que ya pasó.";
export const MENSAJE_REPROGRAMAR_AL_PASADO =
  "No se puede reprogramar un turno a un horario que ya pasó.";

/**
 * Cómo se llama cada estado **en pantalla** (HU-E7-01 RN-02).
 *
 * La historia enumera los cinco con estos nombres exactos, incluido «No se presentó» para
 * `NO_SHOW`. Y **no hay «Reprogramado»**: la misma regla dice que reprogramar no es un estado.
 */
export const ETIQUETAS_DE_ESTADO: Readonly<Record<EstadoTurno, string>> = {
  RESERVADO: "Reservado",
  CONFIRMADO: "Confirmado",
  CANCELADO: "Cancelado",
  COMPLETADO: "Completado",
  NO_SHOW: "No se presentó",
};

export class ErrorDeTurno extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = "ErrorDeTurno";
  }
}

interface CuerpoDeError {
  readonly error?: string;
  readonly detalle?: string;
}

async function fallar(respuesta: Response): Promise<never> {
  const cuerpo = (await respuesta.json().catch(() => ({}))) as CuerpoDeError;
  // `detalle` primero: en un 422 la frase del backend es la que escribió la historia.
  throw new ErrorDeTurno(cuerpo.detalle ?? cuerpo.error ?? "No se pudo completar la operacion");
}

/**
 * El query string de un objeto de filtros, salteando los vacíos.
 *
 * Toma un objeto de forma libre y no `FiltrosDeAgenda`: también lo usa la consulta de
 * disponibilidad, cuyos parámetros son otros. Una firma por cada juego de filtros sería la
 * misma función escrita dos veces.
 */
function consultaDe(filtros: Readonly<Record<string, string | undefined>>): string {
  const parametros = new URLSearchParams();
  for (const [clave, valor] of Object.entries(filtros)) {
    if (valor !== undefined && valor !== "") {
      parametros.set(clave, valor);
    }
  }
  const texto = parametros.toString();
  return texto === "" ? "" : `?${texto}`;
}

export async function listarTurnos(filtros: FiltrosDeAgenda = {}): Promise<ListadoDeTurnos> {
  const respuesta = await fetch(`/api/turnos${consultaDe({ ...filtros })}`, {
    cache: "no-store",
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as ListadoDeTurnos;
}

export async function verTurno(turnoId: string): Promise<Turno> {
  const respuesta = await fetch(`/api/turnos/${turnoId}`, { cache: "no-store" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Turno;
}

export async function verDisponibilidad(recursoId: string, fecha: string): Promise<Disponibilidad> {
  const respuesta = await fetch(
    `/api/turnos/disponibilidad${consultaDe({ recurso_id: recursoId, fecha })}`,
    { cache: "no-store" },
  );
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Disponibilidad;
}

export async function reservarTurno(datos: TurnoNuevo): Promise<Turno> {
  const respuesta = await fetch("/api/turnos", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(datos),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Turno;
}

/** HU-E7-02. Sin cuerpo: cancelar un turno no pide motivo, a diferencia de cancelar un cobro. */
export async function cancelarTurno(turnoId: string): Promise<Turno> {
  const respuesta = await fetch(`/api/turnos/${turnoId}/cancelacion`, { method: "POST" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Turno;
}

/**
 * HU-E7-02. `aPosteriori` es la corrección a posteriori del Administrador (RN-07): sólo viaja
 * cuando es `true`, así que el cuerpo de una reprogramación normal no cambia.
 */
export async function reprogramarTurno(
  turnoId: string,
  inicio: string,
  aPosteriori = false,
): Promise<Turno> {
  const respuesta = await fetch(`/api/turnos/${turnoId}/reprogramacion`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(aPosteriori ? { inicio, a_posteriori: true } : { inicio }),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Turno;
}

/**
 * HU-E7-03. Una sola función para las dos marcas: son la misma decisión con dos valores.
 *
 * Dos funciones —`marcarCompletado` y `marcarNoShow`— habrían hecho que la pantalla tuviera
 * que elegir cuál llamar en lugar de mandar lo que el usuario apretó.
 */
export async function registrarAsistencia(turnoId: string, asistio: boolean): Promise<Turno> {
  const respuesta = await fetch(`/api/turnos/${turnoId}/asistencia`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ asistio }),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Turno;
}

/** Qué tono de badge le toca a cada estado. */
export function tonoDeEstado(estado: EstadoTurno): "ok" | "atencion" | "pendiente" | "error" {
  if (estado === "COMPLETADO") {
    return "ok";
  }
  if (estado === "NO_SHOW") {
    return "error";
  }
  if (estado === "CONFIRMADO" || estado === "RESERVADO") {
    return "atencion";
  }
  return "pendiente";
}

/**
 * La hora de un turno, en la zona del navegador.
 *
 * El backend manda ISO con zona, así que esto no interpreta nada: sólo lo muestra. La agenda
 * la mira gente que está en el local, así que la zona del navegador es la correcta.
 *
 * **`hour12: false` explícito.** Sin él, el ICU de algunos entornos devuelve «03:00 p. m.»
 * para `es-AR` — que no es como se escribe una hora en Argentina, y que además hace que dos
 * turnos consecutivos no se puedan comparar de un vistazo en una columna.
 */
export function horaDe(iso: string): string {
  return new Date(iso).toLocaleTimeString("es-AR", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function dosDigitos(numero: number): string {
  return String(numero).padStart(2, "0");
}

/**
 * Hoy, en la zona del navegador y con el formato de un `<input type="date">` (`AAAA-MM-DD`).
 *
 * **Es una cortesía de interfaz para el atributo `min`, no una regla**: quien rechaza un turno
 * en el pasado es el backend (D95), que compara el instante. Por eso se calcula después de
 * montar, en el navegador, y no en el render del servidor: el servidor puede estar en otra zona
 * y escribir un día distinto.
 */
export function fechaDeHoy(ahora: Date = new Date()): string {
  return `${ahora.getFullYear()}-${dosDigitos(ahora.getMonth() + 1)}-${dosDigitos(ahora.getDate())}`;
}

/** Ahora, con el formato de un `<input type="datetime-local">` (`AAAA-MM-DDTHH:mm`). Ídem. */
export function instanteDeAhora(ahora: Date = new Date()): string {
  return `${fechaDeHoy(ahora)}T${dosDigitos(ahora.getHours())}:${dosDigitos(ahora.getMinutes())}`;
}

/**
 * El día que va en el cintillo de la agenda: «lunes 7 de septiembre».
 *
 * **La zona es fija y no la del navegador**, al revés que en `horaDe`. Este texto lo dibuja un
 * componente de cliente que Next renderiza primero en el servidor: si cada lado eligiera su
 * propia zona, el servidor podría escribir «domingo 6» y el navegador «lunes 7», y React
 * descartaría el HTML entero por no coincidir. La hora de un turno se lee de a una y en el
 * local; el encabezado tiene que ser el mismo texto en los dos renders.
 */
export function fechaLargaDe(iso: string): string {
  return new Date(iso).toLocaleDateString(PREFERENCIAS_POR_DEFECTO.idioma, {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone: PREFERENCIAS_POR_DEFECTO.zonaHoraria,
  });
}
