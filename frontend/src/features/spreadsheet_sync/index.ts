/**
 * Public entry point of the `spreadsheet_sync` feature (rule R5).
 *
 * A route composes what is exported here; nothing outside reaches into the folders below.
 * The imports are relative for the reason the other barrels explain: the
 * `@/features/<name>/…` alias means "somebody reaching into a feature from outside", which
 * is exactly what the lint rule forbids, and a barrel importing its own modules is not
 * that.
 */

export { IngestaDePlanillas } from "./components/IngestaDePlanillas";
export type { PropsDeIngesta } from "./components/IngestaDePlanillas";
export {
  ETIQUETAS_DE_PROVEEDOR,
  EXTENSIONES_ACEPTADAS,
  ErrorDePlanilla,
  LIMITE_TAMANO_BYTES,
  LIMITE_TAMANO_MB,
  MENSAJE_ARCHIVO_DEMASIADO_GRANDE,
  MENSAJE_FORMATO_NO_ACEPTADO,
  desvincularPlanilla,
  iniciarVinculacionConGoogle,
  listarPlanillas,
  subirPlanilla,
  validarArchivo,
} from "./api/planilla";
export type {
  DireccionSync,
  ListadoDeVinculos,
  ProveedorPlanilla,
  Vinculo,
} from "./api/planilla";
