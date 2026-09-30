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
export { SelectorDeClientes } from "./components/SelectorDeClientes";
export type {
  ClienteSeleccionado,
  PropsDeSelectorDeClientes,
} from "./components/SelectorDeClientes";
export {
  ErrorDeCatalogo,
  cambiarEstadoDeCliente,
  consultarPadron,
  crearCliente,
  editarCliente,
  listarClientes,
  verCliente,
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

export { ListadoDeServicios } from "./components/ListadoDeServicios";
export type { PropsDeListadoDeServicios } from "./components/ListadoDeServicios";
export { FormularioDeServicio } from "./components/FormularioDeServicio";
export type { PropsDeFormularioDeServicio } from "./components/FormularioDeServicio";
export {
  ETIQUETAS_DE_ALICUOTA,
  ErrorDeServicio,
  cambiarEstadoDeServicio,
  crearServicio,
  editarServicio,
  listarServicios,
} from "./api/servicio";
export type {
  AlicuotaIVA,
  DatosDeServicio,
  FiltrosDeServicios,
  ListadoDeServicios as ListadoDeServiciosRespuesta,
  Servicio,
} from "./api/servicio";

export { ListadoDeCategorias } from "./components/ListadoDeCategorias";
export type { PropsDeListadoDeCategorias } from "./components/ListadoDeCategorias";
export { FormularioDeCategoria } from "./components/FormularioDeCategoria";
export type { PropsDeFormularioDeCategoria } from "./components/FormularioDeCategoria";
export { SelectorDeCategorias } from "./components/SelectorDeCategorias";
export type { PropsDeSelector } from "./components/SelectorDeCategorias";
export {
  ETIQUETAS_DE_AMBITO,
  ErrorDeCategoria,
  categoriasDeCliente,
  categoriasDeServicio,
  clasificarCliente,
  clasificarServicio,
  crearCategoria,
  editarCategoria,
  eliminarCategoria,
  listarCategorias,
} from "./api/categoria";
export type {
  AmbitoDeCategoria,
  Categoria,
  DatosDeCategoria,
  ListadoDeCategorias as ListadoDeCategoriasRespuesta,
} from "./api/categoria";
