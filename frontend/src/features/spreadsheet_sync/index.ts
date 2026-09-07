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
export { RevisionDeMapeo } from "./components/RevisionDeMapeo";
export type { PropsDeRevision } from "./components/RevisionDeMapeo";
export type { PropsDeIngesta } from "./components/IngestaDePlanillas";
export {
  ATRIBUTOS_DE_CLIENTE,
  ETIQUETAS_DE_ATRIBUTO,
  ETIQUETAS_DE_PROVEEDOR,
  EXTENSIONES_ACEPTADAS,
  ErrorDePlanilla,
  LIMITE_TAMANO_BYTES,
  LIMITE_TAMANO_MB,
  MENSAJE_ARCHIVO_DEMASIADO_GRANDE,
  MENSAJE_FALTAN_OBLIGATORIAS,
  MENSAJE_FORMATO_NO_ACEPTADO,
  confirmarMapeo,
  corregirMapeo,
  desvincularPlanilla,
  iniciarVinculacionConGoogle,
  listarPlanillas,
  proponerMapeo,
  subirPlanilla,
  validarArchivo,
} from "./api/planilla";
export type {
  DireccionSync,
  EntradaDeMapeo,
  Mapeo,
  NivelDeConfianza,
  ListadoDeVinculos,
  ProveedorPlanilla,
  Vinculo,
} from "./api/planilla";
