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

export { AnularComprobante } from "./components/AnularComprobante";
export type { PropsDeAnularComprobante } from "./components/AnularComprobante";
export { ElegirCliente } from "./components/ElegirCliente";
export type { PropsDeElegirCliente } from "./components/ElegirCliente";
export { DetalleDeComprobante } from "./components/DetalleDeComprobante";
export type { PropsDeDetalleDeComprobante } from "./components/DetalleDeComprobante";
export { ListadoDeComprobantes } from "./components/ListadoDeComprobantes";
export type { PropsDeListadoDeComprobantes } from "./components/ListadoDeComprobantes";
export { NuevaEmision } from "./components/NuevaEmision";
export type { PropsDeNuevaEmision } from "./components/NuevaEmision";
export { PuntosDeVenta } from "./components/PuntosDeVenta";
export type { PropsDePuntosDeVenta } from "./components/PuntosDeVenta";
export {
  ETIQUETAS_DE_TIPO,
  ErrorDePuntoDeVenta,
  MENSAJE_DUPLICADO,
  MENSAJE_NO_HABILITADO,
  cambiarEstadoDePuntoDeVenta,
  listarPuntosDeVenta,
  notaDeCreditoDe,
  registrarPuntoDeVenta,
  resumenDeNumeracion,
} from "./api/puntoDeVenta";
export type {
  DatosDePuntoDeVenta,
  ListadoDePuntosDeVenta,
  PuntoDeVenta,
  TipoComprobante,
} from "./api/puntoDeVenta";
export {
  ALICUOTAS,
  ETIQUETAS_DE_ESTADO,
  ErrorDeComprobante,
  MENSAJE_MONTO_EXCEDIDO,
  MENSAJE_SIN_ITEMS,
  MENSAJE_SIN_ORIGEN,
  MENSAJE_SIN_RESULTADOS,
  emitirComprobante,
  emitirNotaDeCredito,
  listarComprobantes,
  numeroFormateado,
  tonoDeEstado,
  validarReceptor,
  verAnulacion,
  verComprobante,
} from "./api/comprobante";
export type {
  Anulacion,
  Comprobante,
  ComprobanteNuevo,
  EstadoComprobante,
  FiltrosDeComprobante,
  ItemDeComprobante,
  ItemNuevo,
  ListadoDeComprobantes as ListadoDeComprobantesRespuesta,
  ReceptorValidado,
} from "./api/comprobante";
