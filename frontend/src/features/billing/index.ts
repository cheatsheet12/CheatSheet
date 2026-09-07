/**
 * billing — BC6, Core.
 *
 * Screens: issue Comprobante, credit notes, points of sale.
 *
 * This file is the feature's PUBLIC ENTRY POINT. Other features may only import
 * from here (rule R5); everything under api/, components/ and hooks/ is internal.
 * Anything genuinely shared belongs in @/shared instead.
 *
 * The imports are relative for the reason the other barrels explain: the
 * `@/features/<name>/…` alias means "somebody reaching into a feature from outside",
 * which is exactly what the lint rule forbids, and a barrel importing its own modules is
 * not that.
 */

export { PuntosDeVenta } from "./components/PuntosDeVenta";
export type { PropsDePuntosDeVenta } from "./components/PuntosDeVenta";
export {
  ETIQUETAS_DE_TIPO,
  ErrorDePuntoDeVenta,
  MENSAJE_DUPLICADO,
  MENSAJE_NO_HABILITADO,
  cambiarEstadoDePuntoDeVenta,
  listarPuntosDeVenta,
  registrarPuntoDeVenta,
  resumenDeNumeracion,
} from "./api/puntoDeVenta";
export type {
  DatosDePuntoDeVenta,
  ListadoDePuntosDeVenta,
  PuntoDeVenta,
  TipoComprobante,
} from "./api/puntoDeVenta";
