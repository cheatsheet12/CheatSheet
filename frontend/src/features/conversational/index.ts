/**
 * conversational — BC9, Core.
 *
 * Pantallas: la bandeja de conversaciones del operador, el hilo abierto con su escalamiento,
 * las respuestas frecuentes del agente y las plantillas de notificación.
 *
 * Este archivo es el PUNTO DE ENTRADA PÚBLICO de la feature. Las demás features sólo pueden
 * importar desde acá (regla R5); todo lo que está bajo api/, components/ y hooks/ es interno.
 */

export { BandejaDeConversaciones } from "./components/BandejaDeConversaciones";
export type { PropsDeBandejaDeConversaciones } from "./components/BandejaDeConversaciones";
export { HiloDeConversacion } from "./components/HiloDeConversacion";
export type { PropsDeHiloDeConversacion } from "./components/HiloDeConversacion";
export { PlantillasDeNotificacion } from "./components/PlantillasDeNotificacion";
export type { PropsDePlantillasDeNotificacion } from "./components/PlantillasDeNotificacion";
export { RespuestasFrecuentes } from "./components/RespuestasFrecuentes";
export type { PropsDeRespuestasFrecuentes } from "./components/RespuestasFrecuentes";
export {
  ETIQUETAS_DE_INTENCION,
  ETIQUETAS_DE_ORIGEN,
  ErrorDeConversacion,
  MENSAJE_SIN_CONVERSACIONES,
  MENSAJE_SIN_ESCALADAS,
  MENSAJE_TOMAR_PRIMERO,
  cerrarEscalamiento,
  listarConversaciones,
  responder,
  tomarEscalamiento,
  tonoDeEscalamiento,
  verConversacion,
} from "./api/conversacion";
export type {
  Conversacion,
  DetalleDeConversacion,
  DireccionMensaje,
  EstadoConversacion,
  EstadoEscalamiento,
  Intencion,
  ListadoDeConversaciones,
  Mensaje,
  OrigenDelMensaje,
} from "./api/conversacion";
export {
  ETIQUETAS_DE_APROBACION,
  ETIQUETAS_DE_CODIGO,
  ErrorDeFaq,
  MENSAJE_CAMPOS_OBLIGATORIOS,
  MENSAJE_CONFIRMAR_BAJA,
  MENSAJE_SIN_FAQS,
  MENSAJE_VARIABLE_INVALIDA,
  crearFaq,
  editarFaq,
  editarPlantilla,
  eliminarFaq,
  listarFaqs,
  listarPlantillas,
  variablesDe,
  variablesInvalidas,
} from "./api/faq";
export type {
  CanalDePlantilla,
  EstadoDeAprobacion,
  Faq,
  ListadoDeFaqs,
  ListadoDePlantillas,
  Plantilla,
} from "./api/faq";
