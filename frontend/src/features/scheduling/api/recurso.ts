/**
 * What PAN-AGE-03 calls (HU-E7-04, HU-E7-05).
 *
 * **No hay `eliminar`.** HU-E7-04 RN-03 pide desactivar: un recurso borrado dejaría los turnos
 * que se prestaron en él apuntando a algo que ya no existe.
 *
 * **Las tres configuraciones reemplazan, no acumulan.** Un recurso tiene un horario de
 * atención y una lista de servicios; guardarlos por partes obligaría a decidir qué pasa cuando
 * una franja nueva pisa a otra vieja, y esa decisión no la pide ninguna historia.
 */

export type TipoRecurso = "PERSONA" | "ESPACIO" | "EQUIPO";
export type TipoExcepcion = "BLOQUEO" | "APERTURA_ESPECIAL";

export interface Patron {
  readonly dia_semana: number;
  /** `"09:00:00"`. Hora local del recurso; el backend la guarda como `time`. */
  readonly hora_inicio: string;
  readonly hora_fin: string;
  readonly duracion_slot_min: number;
}

export interface Excepcion {
  readonly fecha: string;
  readonly tipo: TipoExcepcion;
  readonly franja_inicio: string | null;
  readonly franja_duracion_min: number | null;
}

export interface Recurso {
  readonly id: string;
  readonly nombre: string;
  readonly tipo: TipoRecurso;
  readonly activo: boolean;
  readonly patrones: readonly Patron[];
  readonly excepciones: readonly Excepcion[];
  readonly servicios: readonly string[];
  /** HU-E7-04 RN-06: minutos que se agregan después de cada turno. 0 por defecto. */
  readonly intervalo_entre_turnos_min: number;
}

export interface ListadoDeRecursos {
  readonly recursos: readonly Recurso[];
}

export interface ServicioAgendable {
  readonly id: string;
  readonly nombre: string;
  readonly duracion_estandar_min: number;
}

/** HU-E7-04 y HU-E7-05, palabra por palabra. */
export const MENSAJE_HORARIO_INVERTIDO = "La hora de inicio debe ser anterior a la hora de fin.";
export const MENSAJE_EXCEPCION_DUPLICADA =
  "Ya existe una excepción para esa fecha en este recurso.";
export const MENSAJE_SIN_RECURSOS =
  "Todavía no configuraste ningún recurso. Sin al menos uno activo no se pueden reservar turnos.";

/**
 * Lunes 0, domingo 6 — el orden de Python, que es el que el backend guarda.
 *
 * El índice del arreglo **es** el valor de `dia_semana`. Un mapa `{1: "Lunes"}` sería la misma
 * tabla con una oportunidad más de corrimiento.
 */
export const DIAS: readonly string[] = [
  "Lunes",
  "Martes",
  "Miércoles",
  "Jueves",
  "Viernes",
  "Sábado",
  "Domingo",
];

export const ETIQUETAS_DE_TIPO: Readonly<Record<TipoRecurso, string>> = {
  PERSONA: "Persona",
  ESPACIO: "Espacio",
  EQUIPO: "Equipo",
};

export const ETIQUETAS_DE_EXCEPCION: Readonly<Record<TipoExcepcion, string>> = {
  BLOQUEO: "Sin atención",
  APERTURA_ESPECIAL: "Horario especial",
};

export class ErrorDeRecurso extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = "ErrorDeRecurso";
  }
}

interface CuerpoDeError {
  readonly error?: string;
  readonly detalle?: string;
}

async function fallar(respuesta: Response): Promise<never> {
  const cuerpo = (await respuesta.json().catch(() => ({}))) as CuerpoDeError;
  throw new ErrorDeRecurso(cuerpo.detalle ?? cuerpo.error ?? "No se pudo completar la operacion");
}

export async function listarRecursos(soloActivos = false): Promise<ListadoDeRecursos> {
  const consulta = soloActivos ? "?solo_activos=true" : "";
  const respuesta = await fetch(`/api/recursos${consulta}`, { cache: "no-store" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as ListadoDeRecursos;
}

export async function listarServiciosAgendables(): Promise<readonly ServicioAgendable[]> {
  const respuesta = await fetch("/api/recursos/servicios", { cache: "no-store" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as readonly ServicioAgendable[];
}

export async function registrarRecurso(datos: {
  readonly nombre: string;
  readonly tipo: TipoRecurso;
  readonly patrones: readonly Patron[];
  readonly servicios: readonly string[];
}): Promise<Recurso> {
  const respuesta = await fetch("/api/recursos", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(datos),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Recurso;
}

/**
 * Reemplaza el horario semanal y, si se pasa, el intervalo entre turnos (HU-E7-04 RN-06).
 *
 * Sin intervalo el backend conserva el actual. Los rangos —slot de 5 a 480, intervalo de 0 a
 * 480— los decide el backend y su mensaje se muestra tal cual: los `min` y `max` de los campos
 * son una cortesía.
 */
export async function configurarDisponibilidad(
  recursoId: string,
  patrones: readonly Patron[],
  intervaloEntreTurnosMin?: number,
): Promise<Recurso> {
  const respuesta = await fetch(`/api/recursos/${recursoId}/disponibilidad`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(
      intervaloEntreTurnosMin === undefined
        ? { patrones }
        : { patrones, intervalo_entre_turnos_min: intervaloEntreTurnosMin },
    ),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Recurso;
}

export async function asociarServicios(
  recursoId: string,
  servicios: readonly string[],
): Promise<Recurso> {
  const respuesta = await fetch(`/api/recursos/${recursoId}/servicios`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ servicios }),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Recurso;
}

export async function cambiarEstadoDeRecurso(recursoId: string, activo: boolean): Promise<Recurso> {
  const respuesta = await fetch(`/api/recursos/${recursoId}/estado`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ activo }),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Recurso;
}

export async function registrarExcepcion(
  recursoId: string,
  excepcion: {
    readonly fecha: string;
    readonly tipo: TipoExcepcion;
    readonly franja_inicio?: string | null;
    readonly franja_duracion_min?: number | null;
  },
): Promise<Recurso> {
  const respuesta = await fetch(`/api/recursos/${recursoId}/excepciones`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(excepcion),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Recurso;
}

/**
 * Saca la excepción de una fecha.
 *
 * **El único borrado de la feature**, y no borra una entidad del negocio: una excepción es una
 * anotación sobre un calendario, y sacarla es volver al horario habitual.
 */
export async function quitarExcepcion(recursoId: string, fecha: string): Promise<Recurso> {
  const respuesta = await fetch(`/api/recursos/${recursoId}/excepciones/${fecha}`, {
    method: "DELETE",
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Recurso;
}

/** El horario de un día, legible: `"09:00 a 18:00"`. */
export function horarioDe(patron: Patron): string {
  return `${patron.hora_inicio.slice(0, 5)} a ${patron.hora_fin.slice(0, 5)}`;
}
