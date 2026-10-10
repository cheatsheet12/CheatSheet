/**
 * Por qué falló un envío de WhatsApp, dicho en castellano (U7, D-U7-7).
 *
 * El backend guarda un código de Meta (`131047`) o una clase corta que arma él mismo
 * (`motivo_de_falla_de`: `INCIERTO`, `SATURADA`…), nunca el texto del error: ese texto puede traer el
 * número del cliente. La pantalla es quien lo traduce. Lo que no conoce se muestra con su código crudo,
 * para que soporte pueda buscarlo en la documentación de Meta, y nunca se inventa una explicación.
 *
 * Lo comparten el detalle de un cobro (recordatorios) y el hilo de una conversación (avisos y
 * respuestas), por eso vive en `shared/`: dos features no pueden importarse entre sí (R5).
 */

const MOTIVOS: Readonly<Record<string, string>> = {
  // Códigos de Meta (https://developers.facebook.com/documentation/business-messaging/whatsapp/support/error-codes)
  "131047": "Fuera de la ventana de 24 h y sin plantilla aprobada",
  "131026": "El número no usa WhatsApp",
  "131049": "Meta frenó el envío; se puede reintentar mañana",
  "132015": "La plantilla está pausada en Meta",
  "132016": "La plantilla está deshabilitada en Meta",
  // Clases cortas que arma el backend.
  INCIERTO: "No sabemos si llegó: Meta no respondió",
  COBRO_CERRADO: "No se envió: el cobro se cerró",
  SATURADA: "Meta estaba saturado y no aceptó el mensaje",
  RECHAZADO: "Meta rechazó el mensaje",
  SIN_CANAL: "WhatsApp no está conectado",
  ERROR: "Error inesperado al enviar",
};

/** El motivo de una falla en castellano; el código crudo si no lo conocemos; «Sin detalle» si no hay. */
export function motivoDeFalla(codigo: string | null): string {
  if (codigo === null || codigo === "") {
    return "Sin detalle";
  }
  return MOTIVOS[codigo] ?? `Código ${codigo}`;
}
