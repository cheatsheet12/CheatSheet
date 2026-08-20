/**
 * Public entry point of the `identity` feature (rule R5).
 *
 * A route composes what is exported here; nothing outside reaches into the folders
 * below, and the ESLint rule enforces it.
 *
 * **The imports below are relative on purpose.** The `@/features/<name>/…` alias means
 * one thing in this codebase — somebody reaching into a feature from outside — and the
 * lint rule forbids exactly that. A barrel importing its own modules is not that, so it
 * uses relative paths and the rule stays unambiguous instead of needing an exception.
 */

export { BotonDeSalida } from "./components/BotonDeSalida";
export { FormularioDeAceptacion } from "./components/FormularioDeAceptacion";
export { FormularioDeEmpresa } from "./components/FormularioDeEmpresa";
export { FormularioDeIngreso } from "./components/FormularioDeIngreso";
export { FormularioDePreferencias } from "./components/FormularioDePreferencias";
export { ModalDeInvitacion } from "./components/ModalDeInvitacion";
export { TablaDeUsuarios } from "./components/TablaDeUsuarios";
export type {
  ConsultaDePadron,
  EmpresaActual,
  EstadoDePadron,
  EstadoUsuario,
  Preferencias,
  RolUsuario,
  Suscripciones,
  UsuarioDeLaEmpresa,
} from "./api/cliente";
export { errorDeCuit, esCuitValido, formatearCuit, normalizarCuit } from "./validacion/cuit";
