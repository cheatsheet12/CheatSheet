/**
 * observability — BC10, Generic.
 *
 * Pantallas: el log de operaciones con sus filtros (PAN-LOG-01) y el detalle de una operación
 * con su timeline (PAN-LOG-02), el centro de notificaciones (PAN-CFG-NOT) y el alta de
 * solicitudes de soporte (PAN-SOP-01).
 *
 * Este archivo es el PUNTO DE ENTRADA PÚBLICO de la feature. Las demás features sólo pueden
 * importar desde acá (regla R5); todo lo que está bajo api/, components/ y hooks/ es interno.
 */

export { Bitacora } from "./components/Bitacora";
export type { PropsDeBitacora } from "./components/Bitacora";
export { CentroDeNotificaciones } from "./components/CentroDeNotificaciones";
export type { PropsDeCentroDeNotificaciones } from "./components/CentroDeNotificaciones";
export { DetalleDeOperacion } from "./components/DetalleDeOperacion";
export type { PropsDeDetalleDeOperacion } from "./components/DetalleDeOperacion";
export { Soporte } from "./components/Soporte";
export type { PropsDeSoporte } from "./components/Soporte";
export {
  ETIQUETAS_DE_INICIADOR,
  ETIQUETAS_DE_MODULO,
  ETIQUETAS_DE_RESULTADO,
  ErrorDeBitacora,
  MENSAJE_SIN_OPERACIONES,
  TAMANO_DE_PAGINA,
  listarOperaciones,
  verOperacion,
} from "./api/bitacora";
export type {
  DetalleDeOperacion as DetalleDeOperacionRespuesta,
  FiltrosDeBitacora,
  IniciadorDeOperacion,
  ListadoDeOperaciones,
  Operacion,
  ResultadoDeOperacion,
} from "./api/bitacora";
export {
  ETIQUETAS_DE_CATEGORIA,
  ETIQUETAS_DE_ESTADO,
  ErrorDeNotificacion,
  MENSAJE_CAMPOS_OBLIGATORIOS,
  MENSAJE_SIN_NOTIFICACIONES,
  abrirSolicitud,
  listarNotificaciones,
  listarSolicitudes,
  marcarComoLeida,
} from "./api/notificaciones";
export type {
  ListadoDeNotificaciones,
  ListadoDeSolicitudes,
  Notificacion,
  PrioridadDeSoporte,
  Severidad,
  Solicitud,
  SolicitudNueva,
} from "./api/notificaciones";
