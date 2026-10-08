/**
 * business_config — BC3, Supporting.
 *
 * Screens: business rules, notification templates.
 *
 * This file is the feature's PUBLIC ENTRY POINT. Other features may only import
 * from here (rule R5); everything under api/, components/ and hooks/ is internal.
 * Anything genuinely shared belongs in @/shared instead.
 */

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
