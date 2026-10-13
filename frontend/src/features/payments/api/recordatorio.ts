/** Un recordatorio de la cadena de un cobro, tal como lo manda el detalle (PAN-COB-02). */

export interface Recordatorio {
  readonly id: string;
  readonly paso: number;
  readonly canal: string;
  readonly enviado_en: string | null;
  readonly estado_entrega: string | null;
  /** Cuántos envíos empezaron (U7). */
  readonly intentos: number;
  /**
   * Cuándo toca el próximo intento. El backend lo manda **solo** mientras el recordatorio espera un
   * reintento: en un envío en curso es la ventana de la reserva y no se expone.
   */
  readonly proximo_intento_en: string | null;
  /** Por qué falló: un código de Meta o una clase corta (`INCIERTO`, `COBRO_CERRADO`…). */
  readonly ultimo_error: string | null;
}

/**
 * Cuántos intentos de envío entre barridos hace el backend con un recordatorio (`REINTENTOS_MAXIMOS`
 * en `payments/domain/recordatorio.py`). Solo se usa para decir «intento 2 de 3».
 */
export const INTENTOS_MAXIMOS_DE_RECORDATORIO = 3;
