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
  /** HU-E9-04 RN-02: cuántas veces se usó en el período. */
  readonly usos: number;
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
