/**
 * scheduling — BC8, Core.
 *
 * Pantallas: la agenda de turnos, el detalle de un turno, el alta manual y la configuración de
 * recursos reservables con su disponibilidad.
 *
 * Este archivo es el PUNTO DE ENTRADA PÚBLICO de la feature. Las demás features sólo pueden
 * importar desde acá (regla R5); todo lo que está bajo api/, components/ y hooks/ es interno.
 *
 * Los imports son relativos por lo que explican los otros barriles: el alias
 * `@/features/<name>/…` significa «alguien de afuera metiéndose en una feature», que es
 * justamente lo que la regla prohíbe, y un barril importando sus propios módulos no es eso.
 */

export { AgendaDelDia } from "./components/AgendaDelDia";
export type { PropsDeAgendaDelDia } from "./components/AgendaDelDia";
export { DetalleDeTurno } from "./components/DetalleDeTurno";
export type { PropsDeDetalleDeTurno } from "./components/DetalleDeTurno";
export { NuevoTurno } from "./components/NuevoTurno";
export type { PropsDeNuevoTurno } from "./components/NuevoTurno";
export { RecursosReservables } from "./components/RecursosReservables";
export type { PropsDeRecursosReservables } from "./components/RecursosReservables";
export {
  ETIQUETAS_DE_ESTADO,
  ErrorDeTurno,
  MENSAJE_HORARIO_OCUPADO,
  MENSAJE_NO_TRANSCURRIO,
  MENSAJE_SIN_TURNOS,
  cancelarTurno,
  fechaLargaDe,
  horaDe,
  listarTurnos,
  registrarAsistencia,
  reprogramarTurno,
  reservarTurno,
  tonoDeEstado,
  verDisponibilidad,
  verTurno,
} from "./api/turno";
export type {
  Disponibilidad,
  EstadoTurno,
  FiltrosDeAgenda,
  Horario,
  ListadoDeTurnos,
  Nombrado,
  Turno,
  TurnoNuevo,
} from "./api/turno";
export {
  DIAS,
  ETIQUETAS_DE_EXCEPCION,
  ETIQUETAS_DE_TIPO,
  ErrorDeRecurso,
  MENSAJE_EXCEPCION_DUPLICADA,
  MENSAJE_HORARIO_INVERTIDO,
  MENSAJE_SIN_RECURSOS,
  asociarServicios,
  cambiarEstadoDeRecurso,
  configurarDisponibilidad,
  horarioDe,
  listarRecursos,
  listarServiciosAgendables,
  quitarExcepcion,
  registrarExcepcion,
  registrarRecurso,
} from "./api/recurso";
export type {
  Excepcion,
  ListadoDeRecursos,
  Patron,
  Recurso,
  ServicioAgendable,
  TipoExcepcion,
  TipoRecurso,
} from "./api/recurso";
