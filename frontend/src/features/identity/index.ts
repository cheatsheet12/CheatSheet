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

export { AvisoDePrivacidad } from "./components/AvisoDePrivacidad";
export { BotonDeSalida } from "./components/BotonDeSalida";
export { DocumentoLegalPublico } from "./components/DocumentoLegalPublico";
export { EnlacesLegales } from "./components/EnlacesLegales";
export { FormularioDeAceptacion } from "./components/FormularioDeAceptacion";
export { FormularioDeEmpresa } from "./components/FormularioDeEmpresa";
export { FormularioDeIngreso } from "./components/FormularioDeIngreso";
export { FormularioDeReaceptacion } from "./components/FormularioDeReaceptacion";
export { FormularioDePreferencias } from "./components/FormularioDePreferencias";
export { ModalDeInvitacion } from "./components/ModalDeInvitacion";
export { RenovadorDeSesion } from "./components/RenovadorDeSesion";
export { TablaDeUsuarios } from "./components/TablaDeUsuarios";
export { TextoLegal } from "./components/TextoLegal";
export { VigilanteDeAceptacionLegal } from "./components/VigilanteDeAceptacionLegal";
export type {
  ConsultaDePadron,
  DocumentoLegal,
  DocumentoLegalPublicado,
  EmpresaActual,
  EstadoDePadron,
  EstadoUsuario,
  PendienteLegal,
  PendientesLegales,
  Preferencias,
  RolUsuario,
  Suscripciones,
  UsuarioDeLaEmpresa,
  VersionesVigentes,
} from "./api/cliente";
export { errorDeCuit, esCuitValido, formatearCuit, normalizarCuit } from "./validacion/cuit";
