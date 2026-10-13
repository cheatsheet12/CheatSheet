/** El historial de reembolsos de un cobro (HU-E6-05), tal como lo manda el detalle. */

/** Por dónde salió la plata de un reembolso (ADR-0010): la API de MercadoPago o una carga manual. */
export type OrigenDeReembolso = "API_MERCADOPAGO" | "MANUAL";

/**
 * Una fila del historial de reembolsos (HU-E6-05 RN-08): un reembolso o la corrección de uno.
 *
 * Nunca se edita ni se borra: un error se corrige con **otra fila**, negativa, que apunta a la
 * que anula (`corrige_a`). `corregido` avisa que esta fila ya fue anulada por otra.
 */
export interface Reembolso {
  readonly id: string;
  /** Negativo si y solo si es una corrección. Texto: nunca un `number`. */
  readonly monto: string;
  readonly fecha_devolucion: string;
  readonly origen: OrigenDeReembolso;
  readonly referencia: string | null;
  readonly motivo: string | null;
  readonly corrige_a: string | null;
  readonly corregido: boolean;
}
