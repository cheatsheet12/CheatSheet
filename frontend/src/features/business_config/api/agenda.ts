/**
 * What PAN-CFG-RN calls for the notification agenda (HU-E11-01, HU-E8-04 RN-02).
 *
 * **La agenda de notificación es una regla de negocio más** (`AGENDA_DE_NOTIFICACION`): se lee
 * del mismo `GET /reglas` y se guarda con un `PUT` que **reemplaza**, porque una empresa tiene
 * una agenda y no un catálogo. Cada recordatorio es «N horas antes del turno».
 *
 * La configuración es un JSONB libre en la base (D24: la validación vive en el dominio), así que
 * `leerConfiguracionDeAgenda` descarta lo que no entiende en vez de romper: se muestra lo que se
 * pudo leer y quien la edite la arregla, que es mejor que una página en blanco.
 */

import type { ListadoDeReglasCrudo, ReglaCruda } from "./atencion";

export interface RecordatorioDeAgenda {
  readonly horas_antes: number;
}

export interface ConfiguracionDeAgenda {
  readonly recordatorios: readonly RecordatorioDeAgenda[];
}

export interface AgendaGuardada extends ConfiguracionDeAgenda {
  readonly reglaId: string;
  readonly activa: boolean;
  readonly prioridad: number;
}

export const TIPO_DE_REGLA_DE_AGENDA = "AGENDA_DE_NOTIFICACION";

/** Los topes que impone el dominio; acá deciden mensajes y si «Agregar» está gris. */
export const MINIMO_DE_HORAS = 1;
export const MAXIMO_DE_HORAS = 168;
export const MAXIMO_DE_RECORDATORIOS = 3;

/** Las frases del dominio, palabra por palabra. */
export const MENSAJE_HORAS_FUERA_DE_RANGO = `Las horas de anticipación deben estar entre ${MINIMO_DE_HORAS} y ${MAXIMO_DE_HORAS}.`;
export const MENSAJE_REPETIDOS = "No puede haber dos recordatorios con la misma anticipación.";
export const MENSAJE_SIN_AGENDA =
  "Sin agenda configurada: rige un recordatorio por defecto, 24 horas antes del turno.";
export const MENSAJE_AGENDA_DESACTIVADA =
  "Esta agenda está desactivada en las reglas de negocio: no se envían recordatorios de turno. Guardar la vuelve a activar.";

/** Un solo recordatorio a 24 h, lo que rige sin regla. */
export const HORAS_POR_DEFECTO = 24;

export class ErrorDeAgenda extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = "ErrorDeAgenda";
  }
}

interface CuerpoDeError {
  readonly error?: string;
  readonly detalle?: string;
}

function esObjeto(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === "object" && valor !== null && !Array.isArray(valor);
}

/** Lee la configuración de la regla. Una mal formada se lee vacía; las entradas ilegibles se descartan. */
export function leerConfiguracionDeAgenda(
  configuracion: Record<string, unknown>,
): ConfiguracionDeAgenda {
  const crudos = configuracion["recordatorios"];
  if (!Array.isArray(crudos)) {
    return { recordatorios: [] };
  }
  return {
    recordatorios: crudos.flatMap((entrada: unknown) => {
      if (!esObjeto(entrada) || !Number.isInteger(entrada["horas_antes"])) {
        return [];
      }
      return [{ horas_antes: entrada["horas_antes"] as number }];
    }),
  };
}

function guardadaDe(regla: ReglaCruda): AgendaGuardada {
  return {
    ...leerConfiguracionDeAgenda(regla.configuracion),
    reglaId: regla.id,
    activa: regla.activa,
    prioridad: regla.prioridad,
  };
}

/** La agenda de la empresa, o `null` si nunca configuró una. Prefiere la regla activa. */
export function agendaDe(listado: ListadoDeReglasCrudo): AgendaGuardada | null {
  const reglas = listado.reglas.filter((regla) => regla.tipo === TIPO_DE_REGLA_DE_AGENDA);
  const elegida = reglas.find((regla) => regla.activa) ?? reglas[0];
  return elegida === undefined ? null : guardadaDe(elegida);
}

/**
 * Si la empresa manda recordatorios de turno. Sin agenda rige el de por defecto (encendido); con una,
 * hace falta que esté activa **y** tenga al menos una anticipación: sin ninguna no sale nada, igual
 * que en el backend.
 */
export function recordatoriosEncendidos(agenda: AgendaGuardada | null): boolean {
  return agenda === null || (agenda.activa && agenda.recordatorios.length > 0);
}

async function fallar(respuesta: Response): Promise<never> {
  const cuerpo = (await respuesta.json().catch(() => ({}))) as CuerpoDeError;
  throw new ErrorDeAgenda(cuerpo.detalle ?? cuerpo.error ?? "No se pudo guardar la agenda.");
}

/** `PUT` que **reemplaza** la agenda de la empresa. Sólo el Administrador (lo refuerza el caso de uso). */
export async function configurarAgenda(
  recordatorios: readonly RecordatorioDeAgenda[],
  prioridad = 0,
): Promise<AgendaGuardada> {
  const respuesta = await fetch("/api/reglas/agenda", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ recordatorios, prioridad }),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return guardadaDe((await respuesta.json()) as ReglaCruda);
}
