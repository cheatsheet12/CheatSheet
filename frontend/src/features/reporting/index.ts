/**
 * reporting — BC11, Supporting.
 *
 * Pantallas: el tablero de indicadores con su generador de reportes (PAN-REP-01), la
 * configuración del paquete contable y el acceso del contador (PAN-REP-02), y la página sin
 * sesión a la que llega el contador externo por su enlace.
 *
 * Este archivo es el PUNTO DE ENTRADA PÚBLICO de la feature. Las demás features sólo pueden
 * importar desde acá (regla R5); todo lo que está bajo api/, components/ y hooks/ es interno.
 */

export { AccesoContable } from "./components/AccesoContable";
export type { PropsDeAccesoContable } from "./components/AccesoContable";
export { ConfiguracionDelPaquete } from "./components/ConfiguracionDelPaquete";
export type { PropsDeConfiguracionDelPaquete } from "./components/ConfiguracionDelPaquete";
export { GeneradorDeReportes } from "./components/GeneradorDeReportes";
export type { PropsDeGeneradorDeReportes } from "./components/GeneradorDeReportes";
export { ResumenDeCobros } from "./components/ResumenDeCobros";
export type { PropsDeResumenDeCobros } from "./components/ResumenDeCobros";
export { SelectorDePeriodo } from "./components/SelectorDePeriodo";
export type { PropsDeSelectorDePeriodo } from "./components/SelectorDePeriodo";
export { Tablero } from "./components/Tablero";
export type { PropsDeTablero } from "./components/Tablero";
export {
  ETIQUETAS_DE_ESTADO_DE_REPORTE,
  ETIQUETAS_DE_TIPO,
  ETIQUETAS_DE_TIPO_DE_COMPROBANTE,
  ErrorDeReporte,
  FORMATOS_POR_TIPO,
  MENSAJE_SIN_ACTIVIDAD,
  MENSAJE_SIN_DATOS,
  etiquetaDeSemana,
  generarReporte,
  listarReportes,
  nombreDeSemana,
  nombreDeTipoDeComprobante,
  previsualizar,
  textoDeDia,
  textoDePeriodo,
  urlDeReporte,
  verTablero,
} from "./api/reporte";
export type {
  EstadoReporte,
  FormatoReporte,
  CobrosDeUnEstado,
  ListadoDeReportes,
  Metrica,
  Previsualizacion,
  RangoDePeriodo,
  Reporte,
  Tablero as TableroRespuesta,
  TipoReporte,
} from "./api/reporte";
export {
  CONTENIDOS,
  DIA_MAXIMO_DE_ENVIO,
  ETIQUETAS_DE_CONTENIDO,
  ErrorDePaquete,
  MENSAJE_ACCESO_NO_DISPONIBLE,
  MENSAJE_EMAIL_INVALIDO,
  MENSAJE_SIN_EMAIL,
  generarPaquete,
  guardarConfiguracion,
  invitarContador,
  listarPaquetes,
  nombreDeClaveDePaquete,
  nombreDelPeriodo,
  revocarContador,
  urlDePaquete,
  urlDePaqueteDelContador,
  verAccesoDelContador,
  verConfiguracion,
} from "./api/paquete";
export type {
  AccesoDelContador,
  ConfiguracionDelPaquete as ConfiguracionDelPaqueteRespuesta,
  ConfiguracionNueva,
  ContenidoDelPaquete,
  EstadoDelContador,
  ListadoDePaquetes,
  Paquete,
} from "./api/paquete";
