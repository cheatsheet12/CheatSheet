/**
 * What PAN-WA-02 and PAN-CFG-NOT call (HU-E9-04, HU-E11-02).
 *
 * **`eliminarFaq` existe, y es el único borrado real del sistema.** HU-E9-04 RN-03 pide que una
 * FAQ eliminada deje de estar disponible «de forma inmediata», y una FAQ no es un registro del
 * negocio: no hay nada que auditar en una pregunta que ya no se hace. Todo lo demás en este
 * producto se desactiva.
 *
 * **Las plantillas no tienen alta ni baja.** Los códigos los define el sistema —son los
 * mensajes que el sistema manda— y lo que un administrador hace es editar el cuerpo.
 */

export type CanalDePlantilla = "WHATSAPP" | "EMAIL" | "PANEL";
export type EstadoDeAprobacion = "NO_APLICA" | "PENDIENTE" | "APROBADA" | "RECHAZADA";

export interface Faq {
  readonly id: string;
  readonly pregunta: string;
  readonly respuesta: string;
  /**
   * HU-E9-04 RN-02 (ADR-0012): cuántas veces se usó «Este mes», el «Mes anterior» y en «Total»,
   * con los meses en hora de Argentina. El backend los calcula; la pantalla no suma nada.
   */
  readonly usos_este_mes: number;
  readonly usos_mes_anterior: number;
  readonly usos_total: number;
  /** La última vez que cambió el texto (no cuenta guardar lo mismo ni reindexar). */
  readonly editada_en: string | null;
  /**
   * `true` mientras el vector no se haya calculado. La FAQ existe, se lee y se edita — lo
   * único que no puede es encontrarse por significado. La pantalla lo dice en vez de fingir
   * que está lista.
   */
  readonly sin_indexar: boolean;
}

export interface ListadoDeFaqs {
  readonly faqs: readonly Faq[];
}

/** Por qué no hay comparación antes/después de la edición (HU-E9-04 RN-07). */
export type MotivoSinComparacion = "SIN_EDICIONES" | "EDICION_RECIENTE" | "SIN_HISTORIA_PREVIA";

export interface ParticipacionDeFaq {
  readonly usos: number;
  /** Todas las respuestas con FAQ de la empresa en el lapso. */
  readonly total: number;
  /** Porcentaje con un decimal, como texto (`"12.5"`); `null` si no hubo consultas con FAQ. */
  readonly participacion: string | null;
}

export interface Comparacion {
  readonly dias: number;
  readonly antes: ParticipacionDeFaq;
  readonly despues: ParticipacionDeFaq;
}

export interface DetalleDeUso {
  readonly usos_este_mes: number;
  readonly usos_mes_anterior: number;
  readonly usos_total: number;
  readonly editada_en: string | null;
  readonly comparacion: Comparacion | null;
  readonly motivo_sin_comparacion: MotivoSinComparacion | null;
}

export interface Plantilla {
  readonly id: string;
  readonly codigo: string;
  readonly canal: CanalDePlantilla;
  readonly idioma: string;
  readonly cuerpo: string;
  readonly estado_aprobacion: EstadoDeAprobacion;
  /** Las que admite ese código. La pantalla las ofrece para que nadie las adivine. */
  readonly variables: readonly string[];
  readonly puede_usarse: boolean;
}

export interface ListadoDePlantillas {
  readonly plantillas: readonly Plantilla[];
}

/** HU-E9-04 y HU-E11-02, palabra por palabra. */
export const MENSAJE_CAMPOS_OBLIGATORIOS = "La pregunta y la respuesta son obligatorias.";
export const MENSAJE_VARIABLE_INVALIDA = "La variable indicada no es válida para esta plantilla.";
export const MENSAJE_SIN_FAQS =
  "Todavía no configuraste ninguna respuesta frecuente. El agente deriva a un asesor cada consulta que no puede responder.";
export const MENSAJE_CONFIRMAR_BAJA =
  "El agente va a dejar de usar esta respuesta de inmediato. ¿Seguro?";

/** HU-E9-04 RN-07: lo que el detalle dice cuando no puede comparar. */
export const MENSAJE_SIN_EDICIONES =
  "Esta respuesta nunca se editó: no hay una edición con la cual comparar.";
export const MENSAJE_EDICION_RECIENTE =
  "Se editó hace menos de un día: todavía no hay datos para comparar.";
export const MENSAJE_SIN_HISTORIA_PREVIA =
  "Se editó durante su primer día: no hay historia previa con la cual comparar.";
export const MENSAJE_SIN_CONSULTAS = "Sin consultas respondidas por FAQ";

/**
 * Cómo se lee cada código de plantilla.
 *
 * Un mapa y no el código crudo: `recordatorio_de_cobro` es un identificador del sistema, y una
 * pantalla de configuración que muestra identificadores es una pantalla que obliga a adivinar.
 */
export const ETIQUETAS_DE_CODIGO: Readonly<Record<string, string>> = {
  turno_confirmado: "Confirmación de turno",
  turno_cancelado: "Cancelación de turno",
  turno_reprogramado: "Reprogramación de turno",
  recordatorio_de_turno: "Recordatorio de turno",
  recordatorio_de_cobro: "Recordatorio de cobro",
  cobro_generado: "Link de pago generado",
};

/**
 * Cómo se lee un canal y un idioma.
 *
 * Misma razón que `ETIQUETAS_DE_CODIGO`, aplicada a las otras dos columnas del listado:
 * `WHATSAPP` y `es_AR` son identificadores del sistema, y una pantalla de configuración que
 * imprime `es_AR` seis veces obliga a adivinar de qué idioma habla.
 */
export const ETIQUETAS_DE_CANAL: Readonly<Record<CanalDePlantilla, string>> = {
  WHATSAPP: "WhatsApp",
  EMAIL: "Email",
  PANEL: "Panel",
};

/**
 * Los idiomas que el backend puede mandar hoy.
 *
 * El código es una etiqueta BCP 47 con guion bajo, no un enum cerrado del dominio: si aparece
 * uno que no está acá se muestra crudo, que es más honesto que inventarle un nombre.
 */
export const ETIQUETAS_DE_IDIOMA: Readonly<Record<string, string>> = {
  es_AR: "Español (Argentina)",
  es_ES: "Español (España)",
  es: "Español",
  en_US: "Inglés (Estados Unidos)",
  en: "Inglés",
  pt_BR: "Portugués (Brasil)",
};

/** El idioma legible; un código desconocido se muestra tal cual llegó. */
export function nombreDeIdioma(codigo: string): string {
  return ETIQUETAS_DE_IDIOMA[codigo] ?? codigo;
}

export const ETIQUETAS_DE_APROBACION: Readonly<Record<EstadoDeAprobacion, string>> = {
  NO_APLICA: "No requiere aprobación",
  PENDIENTE: "Pendiente de aprobación",
  APROBADA: "Aprobada",
  RECHAZADA: "Rechazada",
};

export class ErrorDeFaq extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = "ErrorDeFaq";
  }
}

interface CuerpoDeError {
  readonly error?: string;
  readonly detalle?: string;
}

async function fallar(respuesta: Response): Promise<never> {
  const cuerpo = (await respuesta.json().catch(() => ({}))) as CuerpoDeError;
  throw new ErrorDeFaq(cuerpo.detalle ?? cuerpo.error ?? "No se pudo completar la operacion");
}

export async function listarFaqs(): Promise<ListadoDeFaqs> {
  const respuesta = await fetch("/api/faqs", { cache: "no-store" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as ListadoDeFaqs;
}

/** El detalle de PAN-WA-02: los conteos y la participación antes y después de la edición. */
export async function verUsoDeFaq(faqId: string): Promise<DetalleDeUso> {
  const respuesta = await fetch(`/api/faqs/${faqId}/uso`, { cache: "no-store" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as DetalleDeUso;
}

export async function crearFaq(pregunta: string, respuesta: string): Promise<Faq> {
  const salida = await fetch("/api/faqs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pregunta, respuesta }),
  });
  if (!salida.ok) {
    await fallar(salida);
  }
  return (await salida.json()) as Faq;
}

export async function editarFaq(faqId: string, pregunta: string, respuesta: string): Promise<Faq> {
  const salida = await fetch(`/api/faqs/${faqId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pregunta, respuesta }),
  });
  if (!salida.ok) {
    await fallar(salida);
  }
  return (await salida.json()) as Faq;
}

/** HU-E9-04 RN-03. **El único borrado real del sistema** — ver el docstring del módulo. */
export async function eliminarFaq(faqId: string): Promise<void> {
  const respuesta = await fetch(`/api/faqs/${faqId}`, { method: "DELETE" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
}

export async function listarPlantillas(): Promise<ListadoDePlantillas> {
  const respuesta = await fetch("/api/plantillas", { cache: "no-store" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as ListadoDePlantillas;
}

export async function editarPlantilla(plantillaId: string, cuerpo: string): Promise<Plantilla> {
  const respuesta = await fetch(`/api/plantillas/${plantillaId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cuerpo }),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Plantilla;
}

/**
 * Las variables que un texto usa, para poder avisar antes de mandar.
 *
 * **La validación de verdad es del backend** (`{{saldo}}` en un recordatorio de turno es un
 * 422 con la frase de la historia). Esto es la cortesía de decirlo mientras se escribe, no la
 * garantía — dos pestañas pasan cualquier validación del navegador.
 */
export function variablesDe(cuerpo: string): readonly string[] {
  return [...cuerpo.matchAll(/\{\{([a-z_][a-z0-9_]*)\}\}/g)].map((una) => una[1] ?? "");
}

/** Las que el texto usa y la plantilla no admite. Vacío significa que se puede guardar. */
export function variablesInvalidas(
  cuerpo: string,
  admitidas: readonly string[],
): readonly string[] {
  return variablesDe(cuerpo).filter((una) => !admitidas.includes(una));
}
