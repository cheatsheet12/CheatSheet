/**
 * payments — BC7, Core.
 *
 * Pantallas: listado de cobros, detalle, nuevo cobro y las reglas de negocio que gobiernan
 * la cadena de recordatorios.
 *
 * Este archivo es el PUNTO DE ENTRADA PÚBLICO de la feature. Las demás features sólo pueden
 * importar desde acá (regla R5); todo lo que está bajo api/, components/ y hooks/ es interno.
 */

export { DetalleDeCobro } from "./components/DetalleDeCobro";
export type { PropsDeDetalleDeCobro } from "./components/DetalleDeCobro";
export { ListadoDeCobros } from "./components/ListadoDeCobros";
export type { PropsDeListadoDeCobros } from "./components/ListadoDeCobros";
export { NuevoCobro } from "./components/NuevoCobro";
export type { PropsDeNuevoCobro } from "./components/NuevoCobro";
export { ReglasDeNegocio } from "./components/ReglasDeNegocio";
export type { PropsDeReglasDeNegocio } from "./components/ReglasDeNegocio";
export {
  ETIQUETAS_DE_ESTADO,
  ErrorDeCobro,
  LARGO_MINIMO_DE_MOTIVO,
  MENSAJE_LINK_COPIADO,
  MENSAJE_MONTO_NO_POSITIVO,
  MENSAJE_MOTIVO_CORTO,
  MENSAJE_MP_CAIDO,
  MENSAJE_PAGO_HUERFANO,
  MENSAJE_SIN_CONCEPTO,
  MENSAJE_SIN_RESULTADOS,
  cancelarCobro,
  copiarLink,
  generarCobro,
  listarCobros,
  reembolsarCobro,
  regenerarLink,
  tonoDeEstado,
  verCobro,
} from "./api/cobro";
export type {
  Cobro,
  CobroNuevo,
  DetalleDeCobro as DetalleDeCobroRespuesta,
  EstadoCobro,
  FiltrosDeCobro,
  ListadoDeCobros as ListadoDeCobrosRespuesta,
  MetricasDeCobros,
  Recordatorio,
} from "./api/cobro";
export {
  CANALES,
  ETIQUETAS_DE_TIPO,
  ErrorDeRegla,
  MAXIMO_DE_PASOS,
  MENSAJE_DIAS_INVALIDOS,
  cambiarEstadoDeRegla,
  configurarEscalamiento,
  listarReglas,
  pasosDe,
} from "./api/regla";
export type {
  CanalNotificacion,
  ListadoDeReglas,
  PasoDeEscalamiento,
  ReglaDeNegocio,
  TipoRegla,
} from "./api/regla";
