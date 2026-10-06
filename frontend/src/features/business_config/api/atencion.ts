/**
 * What PAN-WA-02 calls for the opening hours (HS-T2 RN-04, HU-E11-01).
 *
 * **El horario de atención es una regla de negocio más** (`HORARIO_DE_ATENCION`): se lee del
 * mismo `GET /reglas` que PAN-CFG-RN y se guarda con un `PUT` que **reemplaza**, porque una
 * empresa tiene un horario y no un catálogo de horarios.
 *
 * La configuración es un JSONB libre en la base (D24: la validación vive en el dominio), así que
 * la pantalla puede recibir cualquier cosa —una fila escrita a mano, una regla de otra versión—.
 * `leerConfiguracion` devuelve una configuración vacía en vez de romper: se muestra vacía y
 * quien la edite la arregla, que es mejor que una página en blanco.
 */

export type PoliticaFueraDeHorario = "AGENTE_RESPONDE" | "MENSAJE_FIJO";

export interface FranjaDeAtencion {
  readonly desde: string;
  readonly hasta: string;
}

export interface DiaDeAtencion {
  /** Lunes 0, como en el backend. */
  readonly dia: number;
  readonly franjas: readonly FranjaDeAtencion[];
}

export interface ConfiguracionDeAtencion {
  readonly dias: readonly DiaDeAtencion[];
  /** Fechas locales `AAAA-MM-DD`: el negocio cerrado todo ese día. */
  readonly fechas_cerradas: readonly string[];
  readonly politica: PoliticaFueraDeHorario;
}

export interface HorarioDeAtencionGuardado extends ConfiguracionDeAtencion {
  readonly reglaId: string;
  readonly activa: boolean;
  readonly prioridad: number;
}

/** Lo mínimo que esta pantalla necesita saber de una regla. */
export interface ReglaCruda {
  readonly id: string;
  readonly tipo: string;
  readonly configuracion: Record<string, unknown>;
  readonly prioridad: number;
  readonly activa: boolean;
}

export interface ListadoDeReglasCrudo {
  readonly reglas: readonly ReglaCruda[];
}

export const TIPO_DE_REGLA = "HORARIO_DE_ATENCION";

export const MENSAJE_SIN_HORARIO =
  "Sin horario configurado: el agente atiende y deriva a cualquier hora.";

/** El tope que impone el dominio. Acá sólo decide si «Agregar fecha» está gris. */
export const MAXIMO_DE_FECHAS = 200;

export const DIAS_DE_LA_SEMANA: readonly string[] = [
  "Lunes",
  "Martes",
  "Miércoles",
  "Jueves",
  "Viernes",
  "Sábado",
  "Domingo",
];

export class ErrorDeAtencion extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = "ErrorDeAtencion";
  }
}

interface CuerpoDeError {
  readonly error?: string;
  readonly detalle?: string;
}

const FECHA = /^\d{4}-\d{2}-\d{2}$/;

function esObjeto(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === "object" && valor !== null && !Array.isArray(valor);
}

function franjasDe(crudas: unknown): FranjaDeAtencion[] {
  if (!Array.isArray(crudas)) {
    return [];
  }
  return crudas.flatMap((franja: unknown) => {
    if (!esObjeto(franja) || typeof franja["desde"] !== "string") {
      return [];
    }
    return typeof franja["hasta"] === "string"
      ? [{ desde: franja["desde"], hasta: franja["hasta"] }]
      : [];
  });
}

function diasDe(crudos: unknown): DiaDeAtencion[] {
  if (!Array.isArray(crudos)) {
    return [];
  }
  return crudos.flatMap((dia: unknown) => {
    if (!esObjeto(dia) || typeof dia["dia"] !== "number") {
      return [];
    }
    const franjas = franjasDe(dia["franjas"]);
    return franjas.length === 0 ? [] : [{ dia: dia["dia"], franjas }];
  });
}

/**
 * Lee la configuración de la regla. Una mal formada se lee vacía; sin `fechas_cerradas` (JSON
 * escrito a mano, versión 1) se lee `[]`.
 */
export function leerConfiguracion(configuracion: Record<string, unknown>): ConfiguracionDeAtencion {
  const fechas = configuracion["fechas_cerradas"];
  return {
    dias: diasDe(configuracion["dias"]),
    fechas_cerradas: Array.isArray(fechas)
      ? fechas.filter((f): f is string => typeof f === "string" && FECHA.test(f))
      : [],
    politica: configuracion["politica"] === "MENSAJE_FIJO" ? "MENSAJE_FIJO" : "AGENTE_RESPONDE",
  };
}

function guardadoDe(regla: ReglaCruda): HorarioDeAtencionGuardado {
  return {
    ...leerConfiguracion(regla.configuracion),
    reglaId: regla.id,
    activa: regla.activa,
    prioridad: regla.prioridad,
  };
}

/** El horario de la empresa, o `null` si nunca configuró uno. Prefiere la regla activa. */
export function horarioDe(listado: ListadoDeReglasCrudo): HorarioDeAtencionGuardado | null {
  const reglas = listado.reglas.filter((regla) => regla.tipo === TIPO_DE_REGLA);
  const elegida = reglas.find((regla) => regla.activa) ?? reglas[0];
  return elegida === undefined ? null : guardadoDe(elegida);
}

async function fallar(respuesta: Response): Promise<never> {
  const cuerpo = (await respuesta.json().catch(() => ({}))) as CuerpoDeError;
  throw new ErrorDeAtencion(cuerpo.detalle ?? cuerpo.error ?? "No se pudo guardar el horario.");
}

/** `PUT` que **reemplaza** el horario de la empresa. Sólo el Administrador (lo refuerza el caso de uso). */
export async function configurarHorarioDeAtencion(
  configuracion: ConfiguracionDeAtencion,
  prioridad = 0,
): Promise<HorarioDeAtencionGuardado> {
  const respuesta = await fetch("/api/reglas/horario-de-atencion", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...configuracion, prioridad }),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return guardadoDe((await respuesta.json()) as ReglaCruda);
}
