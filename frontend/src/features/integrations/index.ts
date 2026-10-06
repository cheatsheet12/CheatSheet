/**
 * Public entry point of the `integrations` feature (rule R5).
 *
 * A route composes what is exported here; nothing outside reaches into the folders below.
 * The imports are relative for the reason `identity`'s barrel explains: the
 * `@/features/<name>/…` alias means "somebody reaching into a feature from outside", which
 * is exactly what the lint rule forbids, and a barrel importing its own modules is not
 * that.
 */

export { GrillaDeIntegraciones } from "./components/GrillaDeIntegraciones";
export type { PropsDeGrilla, RetornoDeAutorizacion } from "./components/GrillaDeIntegraciones";
export {
  listarIntegraciones,
  verificarIntegraciones,
  conectarIntegracion,
  iniciarAutorizacion,
  canjearAutorizacion,
} from "./api/cliente";
export type {
  Ambiente,
  AutorizacionIniciada,
  EstadoDeConexion,
  Integracion,
  ListadoDeIntegraciones,
  SistemaExterno,
} from "./api/cliente";
