/**
 * What PAN-WA-01 calls (HU-E9-01, HU-E9-02).
 *
 * **No hay `eliminar`.** Una conversación es el registro de lo que se le dijo a un cliente, y
 * un escalamiento cerrado es un caso atendido. El backend no otorga el permiso.
 *
 * **`esta_escalada` viene del backend y no se calcula acá.** HU-E9-01 RN-01 dice que la
 * condición se deriva de que exista un escalamiento abierto; derivarla otra vez del lado del
 * cliente sería el mismo hecho calculado en dos lugares, con la posibilidad de que discrepen
 * justo cuando un operador está por escribirle a alguien.
 */

export type EstadoConversacion = "ACTIVA" | "ARCHIVADA";
export type EstadoEscalamiento = "ABIERTO" | "ASIGNADO" | "RESUELTO";
export type DireccionMensaje = "ENTRANTE" | "SALIENTE";
export type OrigenDelMensaje = "AGENTE" | "OPERADOR" | "SISTEMA";
export type Intencion = "TURNO" | "CONSULTA" | "PAGO" | "FAQ" | "DESCONOCIDA";

export interface Mensaje {
  readonly id: string;
  readonly direccion: DireccionMensaje;
  readonly tipo_contenido: string;
  readonly contenido: string;
  readonly momento: string;
  readonly intencion: Intencion | null;
  readonly estado_entrega: string | null;
  /** HU-E9-01 RN-04: lo que hace que el operador se distinga del agente en el historial. */
  readonly origen: OrigenDelMensaje | null;
  /** Por qué falló un saliente (U7): un código de Meta o una clase corta; se traduce en pantalla. */
  readonly motivo_de_falla: string | null;
}

export interface Conversacion {
  readonly id: string;
  readonly cliente_id: string;
  readonly estado: EstadoConversacion;
  readonly ultimo_mensaje_en: string | null;
  readonly esta_escalada: boolean;
  readonly escalamiento_id: string | null;
  readonly motivo: string | null;
  readonly estado_escalamiento: EstadoEscalamiento | null;
  readonly usuario_asignado_id: string | null;
}

export interface DetalleDeConversacion extends Conversacion {
  readonly mensajes: readonly Mensaje[];
}

export interface ListadoDeConversaciones {
  readonly conversaciones: readonly Conversacion[];
}

/** Las historias, palabra por palabra. */
export const MENSAJE_SIN_CONVERSACIONES = "No hay conversaciones para el filtro seleccionado.";
export const MENSAJE_SIN_ESCALADAS = "No hay conversaciones esperando a un asesor.";
export const MENSAJE_TOMAR_PRIMERO =
  "Tomá el escalamiento antes de escribirle al cliente: si no, el agente sigue contestando.";

/**
 * Cómo se lee cada intención **en pantalla**.
 *
 * El valor que viaja es el del dominio; esto es presentación. `DESCONOCIDA` se muestra «Sin
 * clasificar» porque es lo que significa para quien mira: nadie decidió todavía de qué se
 * trata, no que el sistema sepa que es desconocido.
 */
export const ETIQUETAS_DE_INTENCION: Readonly<Record<Intencion, string>> = {
  TURNO: "Turno",
  CONSULTA: "Consulta",
  PAGO: "Pago",
  FAQ: "Pregunta frecuente",
  DESCONOCIDA: "Sin clasificar",
};

/**
 * Cómo se lee **en pantalla** el estado de entrega de un saliente (HU-E8-04 RN-04, U7).
 *
 * El valor que viaja es el del dominio (`LEIDO`); esto es presentación. Un estado que la pantalla no
 * conoce se muestra tal cual en vez de esconderse.
 */
export const ETIQUETAS_DE_ENTREGA: Readonly<Record<string, string>> = {
  ENVIADO: "Enviado",
  ENTREGADO: "Entregado",
  LEIDO: "Leído",
  FALLIDO: "No se pudo enviar",
};

export const ETIQUETAS_DE_ORIGEN: Readonly<Record<OrigenDelMensaje, string>> = {
  AGENTE: "Agente",
  OPERADOR: "Operador",
  SISTEMA: "Sistema",
};

export class ErrorDeConversacion extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = "ErrorDeConversacion";
  }
}

interface CuerpoDeError {
  readonly error?: string;
  readonly detalle?: string;
}

async function fallar(respuesta: Response): Promise<never> {
  const cuerpo = (await respuesta.json().catch(() => ({}))) as CuerpoDeError;
  // `detalle` primero: en un 422 la frase del backend es la que escribió la historia — y para
  // el escalamiento cerrado, ese texto **es** el criterio de aceptación.
  throw new ErrorDeConversacion(
    cuerpo.detalle ?? cuerpo.error ?? "No se pudo completar la operacion",
  );
}

export async function listarConversaciones(
  soloEscaladas = false,
): Promise<ListadoDeConversaciones> {
  const consulta = soloEscaladas ? "?solo_escaladas=true" : "";
  const respuesta = await fetch(`/api/conversaciones${consulta}`, { cache: "no-store" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as ListadoDeConversaciones;
}

export async function verConversacion(conversacionId: string): Promise<DetalleDeConversacion> {
  const respuesta = await fetch(`/api/conversaciones/${conversacionId}`, { cache: "no-store" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as DetalleDeConversacion;
}

/** HU-E9-01 RN-02: a partir de acá el agente deja de contestar ese hilo. */
export async function tomarEscalamiento(escalamientoId: string): Promise<Conversacion> {
  const respuesta = await fetch(`/api/escalamientos/${escalamientoId}/toma`, { method: "POST" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Conversacion;
}

/**
 * HU-E9-02. `devolverAlAgente` decide si el hilo vuelve o se da por finalizado.
 *
 * `clasificacion` es la corrección manual de RN-05: sin ella, el agente reevalúa solo.
 */
export async function cerrarEscalamiento(
  escalamientoId: string,
  devolverAlAgente: boolean,
  clasificacion?: Intencion,
): Promise<Conversacion> {
  const respuesta = await fetch(`/api/escalamientos/${escalamientoId}/cierre`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      devolver_al_agente: devolverAlAgente,
      clasificacion: clasificacion ?? null,
    }),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Conversacion;
}

/**
 * El destino no viaja: el backend lo resuelve del cliente dueño del hilo.
 */
export async function responder(conversacionId: string, texto: string): Promise<Mensaje> {
  const respuesta = await fetch(`/api/conversaciones/${conversacionId}/mensajes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ texto }),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Mensaje;
}

/**
 * La hora de un mensaje, sola, para el renglón de la bandeja.
 *
 * La lista muestra la hora y no la fecha completa porque el ancho de la columna es de tres
 * palabras: una bandeja de mensajería se lee por lo que pasó hoy. La fecha entera sigue
 * estando en el hilo, arriba de cada grupo de mensajes.
 *
 * **`hour12: false` explícito**, por lo mismo que en la agenda: sin él el ICU de algunos
 * entornos devuelve «03:00 p. m.» para `es-AR`, que no es como se escribe una hora en
 * Argentina y hace que dos renglones consecutivos no se puedan comparar de un vistazo.
 */
export function horaDeMensaje(iso: string | null): string {
  if (iso === null || iso.trim() === "") {
    return "—";
  }
  const momento = new Date(iso);
  if (Number.isNaN(momento.getTime())) {
    return "—";
  }
  return momento.toLocaleTimeString("es-AR", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/** Qué tono de badge le toca a un hilo según espere o no a una persona. */
export function tonoDeEscalamiento(estado: EstadoEscalamiento | null): "ok" | "atencion" | "error" {
  if (estado === "ABIERTO") {
    return "error";
  }
  if (estado === "ASIGNADO") {
    return "atencion";
  }
  return "ok";
}
