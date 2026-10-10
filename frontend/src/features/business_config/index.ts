/**
 * business_config — BC3, Supporting.
 *
 * Screens: business rules (incl. the notification agenda), notification templates.
 *
 * This file is the feature's PUBLIC ENTRY POINT. Other features may only import
 * from here (rule R5); everything under api/, components/ and hooks/ is internal.
 * Anything genuinely shared belongs in @/shared instead.
 */

export { AgendaDeNotificacion } from "./components/AgendaDeNotificacion";
export type { PropsDeAgendaDeNotificacion } from "./components/AgendaDeNotificacion";
export {
  ErrorDeAgenda,
  MENSAJE_SIN_AGENDA,
  agendaDe,
  configurarAgenda,
  recordatoriosEncendidos,
} from "./api/agenda";
export type { AgendaGuardada, ConfiguracionDeAgenda, RecordatorioDeAgenda } from "./api/agenda";
export { HorarioDeAtencion } from "./components/HorarioDeAtencion";
export type { PropsDeHorarioDeAtencion } from "./components/HorarioDeAtencion";
export {
  ErrorDeAtencion,
  MENSAJE_SIN_HORARIO,
  configurarHorarioDeAtencion,
  horarioDe,
} from "./api/atencion";
export type {
  ConfiguracionDeAtencion,
  HorarioDeAtencionGuardado,
  ListadoDeReglasCrudo,
  PoliticaFueraDeHorario,
} from "./api/atencion";
