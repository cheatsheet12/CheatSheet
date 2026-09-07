/**
 * What PAN-CFG-RN calls (HU-E11-01).
 *
 * **La regla de escalamiento se reemplaza, no se acumula.** Una empresa tiene una cadena, no
 * un catálogo de cadenas, y por eso el verbo es `PUT`: si cada guardado creara una regla
 * nueva, la resolución por prioridad tendría que desempatar entre versiones de lo mismo.
 */

export type TipoRegla = "ESCALAMIENTO_DE_COBRO" | "POLITICA_DE_TURNO" | "AGENDA_DE_NOTIFICACION";
export type CanalNotificacion = "WHATSAPP" | "EMAIL" | "PANEL";

export interface PasoDeEscalamiento {
  readonly dias: number;
  readonly canal: CanalNotificacion;
}

export interface ReglaDeNegocio {
  readonly id: string;
  readonly tipo: TipoRegla;
  /** El JSONB tal cual. Cada tipo sabe leer el suyo. */
  readonly configuracion: Record<string, unknown>;
  readonly prioridad: number;
  readonly activa: boolean;
  readonly created_at: string;
  readonly updated_at: string | null;
}

export interface ListadoDeReglas {
  readonly reglas: readonly ReglaDeNegocio[];
}

/** HU-E11-01, palabra por palabra. */
export const MENSAJE_DIAS_INVALIDOS = "Los días de escalamiento deben ser mayores a cero.";

/** El tope que impone el dominio. Acá sólo decide si «Agregar paso» está gris. */
export const MAXIMO_DE_PASOS = 6;

export const ETIQUETAS_DE_TIPO: Readonly<Record<TipoRegla, string>> = {
  ESCALAMIENTO_DE_COBRO: "Escalamiento de cobros",
  POLITICA_DE_TURNO: "Política de turnos",
  AGENDA_DE_NOTIFICACION: "Agenda de notificaciones",
};

export const CANALES: readonly { readonly valor: string; readonly etiqueta: string }[] = [
  { valor: "WHATSAPP", etiqueta: "WhatsApp" },
  { valor: "EMAIL", etiqueta: "Email" },
  { valor: "PANEL", etiqueta: "Panel" },
];

export class ErrorDeRegla extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = "ErrorDeRegla";
  }
}

interface CuerpoDeError {
  readonly error?: string;
  readonly detalle?: string;
}

async function fallar(respuesta: Response): Promise<never> {
  const cuerpo = (await respuesta.json().catch(() => ({}))) as CuerpoDeError;
  throw new ErrorDeRegla(cuerpo.detalle ?? cuerpo.error ?? "No se pudo completar la operacion");
}

export async function listarReglas(): Promise<ListadoDeReglas> {
  const respuesta = await fetch("/api/reglas", { cache: "no-store" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as ListadoDeReglas;
}

export async function configurarEscalamiento(
  pasos: readonly PasoDeEscalamiento[],
  prioridad = 0,
): Promise<ReglaDeNegocio> {
  const respuesta = await fetch("/api/reglas/escalamiento", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pasos, prioridad }),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as ReglaDeNegocio;
}

export async function cambiarEstadoDeRegla(
  reglaId: string,
  activa: boolean,
): Promise<ReglaDeNegocio> {
  const respuesta = await fetch(`/api/reglas/${reglaId}/estado`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ activa }),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as ReglaDeNegocio;
}

/**
 * Lee los pasos de una regla de escalamiento.
 *
 * Devuelve `[]` cuando la configuración no tiene la forma esperada, en vez de romper: la
 * pantalla muestra una regla vacía y quien la edite la arregla, que es mejor que una página
 * en blanco por una fila mal escrita a mano en la base.
 */
export function pasosDe(regla: ReglaDeNegocio): PasoDeEscalamiento[] {
  const crudos = regla.configuracion["pasos"];
  if (!Array.isArray(crudos)) {
    return [];
  }
  return crudos.flatMap((paso) => {
    if (typeof paso !== "object" || paso === null) {
      return [];
    }
    const dias = (paso as { dias?: unknown }).dias;
    const canal = (paso as { canal?: unknown }).canal;
    if (typeof dias !== "number" || typeof canal !== "string") {
      return [];
    }
    return [{ dias, canal: canal as CanalNotificacion }];
  });
}
