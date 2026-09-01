/**
 * Public entry point of the `master_data` feature (rule R5).
 *
 * A route composes what is exported here; nothing outside reaches into the folders below.
 * The imports are relative for the reason `integrations`' barrel explains: the
 * `@/features/<name>/…` alias means "somebody reaching into a feature from outside", which
 * is exactly what the lint rule forbids, and a barrel importing its own modules is not
 * that.
 */

export { ListadoDeClientes } from "./components/ListadoDeClientes";
export type { PropsDeListado } from "./components/ListadoDeClientes";
export { FormularioDeCliente } from "./components/FormularioDeCliente";
export type { PropsDeFormulario } from "./components/FormularioDeCliente";
export {
  ErrorDeCatalogo,
  cambiarEstadoDeCliente,
  consultarPadron,
  crearCliente,
  editarCliente,
  listarClientes,
} from "./api/cliente";
export type {
  Cliente,
  CondicionIVA,
  DatosDeCliente,
  DatosDePadron,
  EstadoDeConsulta,
  FiltrosDeListado,
  ListadoDeClientes as ListadoDeClientesRespuesta,
  OrigenDato,
  ResultadoDePadron,
} from "./api/cliente";
