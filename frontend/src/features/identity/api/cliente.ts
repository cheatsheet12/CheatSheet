/**
 * What the onboarding screens call.
 *
 * These talk to **this app's** route handlers, never to the backend directly. The BFF is
 * what holds the session cookie, and a browser cannot attach an HttpOnly cookie it is
 * not allowed to read (ADR-011).
 */

export interface DatosDeRegistro {
  readonly email: string;
  readonly contrasena: string;
  readonly nombre: string;
}

export interface DatosDeIngreso {
  readonly email: string;
  readonly contrasena: string;
}

export interface DatosDeEmpresa {
  readonly razon_social: string;
  readonly cuit: string;
  readonly condicion_iva: string;
  readonly nombre_responsable: string;
  readonly email_contacto: string;
}

export interface ResultadoDeSesion {
  readonly onboarding_completo: boolean;
}

export type RolUsuario = "ADMINISTRADOR" | "OPERADOR" | "SOLO_LECTURA";
export type EstadoUsuario = "INVITADO" | "ACTIVO" | "INACTIVO";

export interface UsuarioDeLaEmpresa {
  readonly id: string;
  readonly email: string;
  readonly nombre: string;
  readonly rol: RolUsuario;
  readonly estado: EstadoUsuario;
  /** Present only while the invitation is pending — it is what resend and revoke act on. */
  readonly invitacion_id: string | null;
}

export interface DatosDeInvitacion {
  readonly email: string;
  readonly rol: RolUsuario;
}

export interface DatosDeAceptacion {
  readonly token: string;
  readonly nombre: string;
  readonly contrasena: string;
}

/** `{"FACTURACION": ["EMAIL", "PANEL"], …}` — the shape of the `pref_suscripciones` column. */
export type Suscripciones = Readonly<Record<string, readonly string[]>>;

export interface Preferencias {
  readonly pref_idioma: string;
  readonly pref_zona_horaria: string;
  readonly pref_suscripciones: Suscripciones;
}

export interface CambioDePreferencias {
  readonly pref_idioma?: string;
  readonly pref_zona_horaria?: string;
  readonly pref_suscripciones?: Suscripciones;
}

/** What the BFF answers when something went wrong, already stripped of internals. */
export class ErrorDeFormulario extends Error {
  constructor(readonly detalle: string) {
    super(detalle);
    this.name = "ErrorDeFormulario";
  }
}

async function leer<T>(ruta: string): Promise<T> {
  const respuesta = await fetch(ruta, { headers: { Accept: "application/json" } });
  const datos: unknown = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    throw new ErrorDeFormulario(mensajeDe(datos, respuesta.status));
  }
  return datos as T;
}

async function enviar<T>(ruta: string, cuerpo: unknown, method = "POST"): Promise<T> {
  const respuesta = await fetch(ruta, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cuerpo),
  });
  const datos: unknown = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    throw new ErrorDeFormulario(mensajeDe(datos, respuesta.status));
  }
  return datos as T;
}

/**
 * The messages are the ones the behaviour annotations prescribe. The backend answers
 * with a typed error name; turning it into copy is the frontend's job, because the copy
 * is Spanish product language and the API is not.
 */
function mensajeDe(datos: unknown, status: number): string {
  const error =
    typeof datos === "object" && datos !== null && "error" in datos ? String(datos.error) : "";
  switch (error) {
    case "EmailYaRegistrado":
      return "Ese email ya tiene una cuenta. ¿Iniciar sesión?";
    case "CredencialesInvalidas":
      return "Email o contraseña incorrectos.";
    case "CuitYaRegistrado":
      return "Ese CUIT ya está registrado en otra empresa.";
    case "PermisoDenegado":
      return "Tu rol no permite esta acción.";
    case "UltimoAdministradorActivo":
      return "La empresa debe conservar al menos un Administrador activo.";
    case "InvitacionInvalida":
      return "Esta invitación no es válida o ya fue utilizada.";
    case "EntradaInvalida":
      return typeof datos === "object" && datos !== null && "detalle" in datos
        ? String(datos.detalle)
        : "Revisá los datos ingresados.";
    default:
      return status >= 500
        ? "No pudimos completar la operación. Probá de nuevo en unos minutos."
        : "Revisá los datos ingresados.";
  }
}

export async function registrar(datos: DatosDeRegistro): Promise<ResultadoDeSesion> {
  return enviar<ResultadoDeSesion>("/api/auth/registro", datos);
}

export async function ingresar(datos: DatosDeIngreso): Promise<ResultadoDeSesion> {
  return enviar<ResultadoDeSesion>("/api/auth/login", datos);
}

export async function guardarEmpresa(datos: DatosDeEmpresa): Promise<ResultadoDeSesion> {
  return enviar<ResultadoDeSesion>("/api/auth/empresa", datos, "PUT");
}

export async function listarUsuarios(): Promise<readonly UsuarioDeLaEmpresa[]> {
  return leer<readonly UsuarioDeLaEmpresa[]>("/api/usuarios");
}

export async function invitarUsuario(datos: DatosDeInvitacion): Promise<UsuarioDeLaEmpresa> {
  return enviar<UsuarioDeLaEmpresa>("/api/usuarios/invitaciones", datos);
}

export async function reenviarInvitacion(invitacionId: string): Promise<void> {
  await enviar<unknown>(`/api/usuarios/invitaciones/${invitacionId}/reenvio`, {});
}

export async function revocarInvitacion(invitacionId: string): Promise<void> {
  await enviar<unknown>(`/api/usuarios/invitaciones/${invitacionId}`, {}, "DELETE");
}

export async function cambiarRol(usuarioId: string, rol: RolUsuario): Promise<UsuarioDeLaEmpresa> {
  return enviar<UsuarioDeLaEmpresa>(`/api/usuarios/${usuarioId}/rol`, { rol }, "PATCH");
}

export async function desactivarUsuario(usuarioId: string): Promise<UsuarioDeLaEmpresa> {
  return enviar<UsuarioDeLaEmpresa>(`/api/usuarios/${usuarioId}/desactivacion`, {});
}

export async function reactivarUsuario(usuarioId: string): Promise<UsuarioDeLaEmpresa> {
  return enviar<UsuarioDeLaEmpresa>(`/api/usuarios/${usuarioId}/reactivacion`, {});
}

export async function verPreferencias(): Promise<Preferencias> {
  return leer<Preferencias>("/api/usuarios/preferencias");
}

export async function guardarPreferencias(datos: CambioDePreferencias): Promise<Preferencias> {
  return enviar<Preferencias>("/api/usuarios/preferencias", datos, "PUT");
}

/**
 * Accepting an invitation. Public: whoever calls has no session — obtaining one is what
 * accepting gives them.
 */
export async function aceptarInvitacion(datos: DatosDeAceptacion): Promise<ResultadoDeSesion> {
  return enviar<ResultadoDeSesion>("/api/auth/invitaciones/aceptar", datos);
}
