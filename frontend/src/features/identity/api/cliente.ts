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

/** What the BFF answers when something went wrong, already stripped of internals. */
export class ErrorDeFormulario extends Error {
  constructor(readonly detalle: string) {
    super(detalle);
    this.name = "ErrorDeFormulario";
  }
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
