/**
 * What PAN-CFG-INT calls.
 *
 * These talk to **this app's** route handlers, never to the backend directly: the BFF is
 * what holds the session cookie, and a browser cannot attach an HttpOnly cookie it is not
 * allowed to read (ADR-011).
 *
 * **No credential type appears here, and that is deliberate.** The backend never returns
 * one, so the client has no shape to hold it in — the leak that would matter most is the
 * one the type system should make awkward to write.
 */

export type SistemaExterno = "ARCA" | "MERCADOPAGO" | "WHATSAPP" | "GOOGLE_SHEETS" | "EXCEL_ONLINE";

/** The three states of HU-E2-05 RN-02. */
export type EstadoDeConexion = "CONECTADO" | "ATENCION" | "NO_CONECTADO";

export type Ambiente = "HOMOLOGACION" | "PRODUCCION";

export interface Integracion {
  readonly sistema: SistemaExterno;
  readonly estado: EstadoDeConexion;
  readonly detalle: string | null;
  readonly ambiente: Ambiente | null;
  readonly verificado_en: string | null;
  /** False means never connected; true with NO_CONECTADO means connected and now down. */
  readonly configurada: boolean;
}

export interface ListadoDeIntegraciones {
  readonly integraciones: readonly Integracion[];
  readonly verificado_en: string | null;
}

async function pedir<T>(
  ruta: string,
  metodo: "GET" | "POST" | "PUT",
  cuerpo?: unknown,
): Promise<T> {
  const respuesta = await fetch(ruta, {
    method: metodo,
    ...(cuerpo !== undefined
      ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo) }
      : {}),
  });
  const datos: unknown = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    const detalle = (datos as { detalle?: string }).detalle;
    throw new Error(detalle ?? "No se pudo completar la operacion");
  }
  return datos as T;
}

export async function listarIntegraciones(): Promise<ListadoDeIntegraciones> {
  return pedir<ListadoDeIntegraciones>("/api/integraciones", "GET");
}

export async function verificarIntegraciones(): Promise<ListadoDeIntegraciones> {
  return pedir<ListadoDeIntegraciones>("/api/integraciones/verificacion", "POST");
}

export async function conectarIntegracion(
  sistema: SistemaExterno,
  contenido: string,
): Promise<Integracion> {
  return pedir<Integracion>(`/api/integraciones/${sistema}/conexion`, "PUT", {
    contenido,
    parametros: {},
  });
}
