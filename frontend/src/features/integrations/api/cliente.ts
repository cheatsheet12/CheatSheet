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

/**
 * The four states an integration can be in.
 *
 * Three are HU-E2-05 RN-02's. `PENDIENTE` is HU-E2-03's: Meta reviews a phone number for
 * 24 to 72 hours, and during that window the integration is neither connected nor failed.
 */
export type EstadoDeConexion = "CONECTADO" | "PENDIENTE" | "ATENCION" | "NO_CONECTADO";

export type Ambiente = "HOMOLOGACION" | "PRODUCCION";

export interface Integracion {
  readonly sistema: SistemaExterno;
  readonly estado: EstadoDeConexion;
  readonly detalle: string | null;
  readonly ambiente: Ambiente | null;
  readonly verificado_en: string | null;
  /** False means never connected; true with NO_CONECTADO means connected and now down. */
  readonly configurada: boolean;
  /**
   * A short name for what is connected — for WhatsApp, the display name Meta verified
   * plus the number (HU-E2-03 RN-03). The only stored parameter the API returns: the
   * rest either identify the account to the provider or drive a simulation.
   */
  readonly etiqueta: string | null;
  /**
   * Only on the answer to a connection, and only for ARCA: what the taxpayer registry had
   * to say about the company's fiscal data now that it can finally be asked. Connecting
   * ARCA is the first moment the padrón lookup is possible at all, so the finding rides
   * back on the response the Administrator is already looking at.
   */
  readonly aviso_fiscal?: string | null;
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

/** Where the browser has to go to authorize, and how long that link is good for. */
export interface AutorizacionIniciada {
  readonly url: string;
  readonly expira_en_segundos: number;
}

/**
 * Starts an OAuth2 connection (HU-E2-02 RN-01).
 *
 * Returns the URL instead of navigating, so the caller decides when to leave the page —
 * and so this stays a function that can be tested without a browser.
 */
export async function iniciarAutorizacion(sistema: SistemaExterno): Promise<AutorizacionIniciada> {
  return pedir<AutorizacionIniciada>(`/api/integraciones/${sistema}/autorizacion`, "POST");
}

/**
 * Finishes it: the code the provider sent back becomes a stored credential.
 *
 * The `state` is forwarded untouched. Nothing on this side checks it — it is checked
 * where it means something, which is the backend.
 */
export async function canjearAutorizacion(
  sistema: SistemaExterno,
  codigo: string,
  estado: string,
): Promise<Integracion> {
  return pedir<Integracion>(`/api/integraciones/${sistema}/autorizacion/canje`, "POST", {
    codigo,
    estado,
  });
}

/** What a provider needs besides the credential — for Meta, which number and which account. */
export type ParametrosDeConexion = Readonly<Record<string, string>>;

export async function conectarIntegracion(
  sistema: SistemaExterno,
  contenido: string,
  parametros: ParametrosDeConexion = {},
): Promise<Integracion> {
  return pedir<Integracion>(`/api/integraciones/${sistema}/conexion`, "PUT", {
    contenido,
    parametros,
  });
}
