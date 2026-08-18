/**
 * The single door from this app to the backend API.
 *
 * Three things every call gets, because forgetting any of them once is enough:
 *
 * - **A timeout.** `fetch` has none by default. A backend that accepts the connection
 *   and never answers would otherwise hold a server-side render open indefinitely.
 * - **The bearer token from the HttpOnly cookie**, attached here so no feature has to
 *   remember to, and so the token never reaches the browser bundle.
 * - **A typed failure.** Errors come back as a value describing what happened, not as
 *   an exception carrying the backend's internals into a React tree.
 *
 * `any` is forbidden (CLAUDE.md §5), so the response shape is a generic the caller
 * declares — which is the caller admitting it is asserting a contract, rather than
 * pretending the network returns something known.
 */

import { leerToken } from "@/lib/session";

const TIMEOUT_POR_DEFECTO_MS = 10_000;

export class ErrorDeApi extends Error {
  constructor(
    readonly status: number,
    readonly detalle: string,
    /**
     * The exception class name the API sends in `error` — `EmailYaRegistrado`,
     * `CredencialesInvalidas`. It is what a caller should branch on: matching against
     * `detalle` would couple the UI to a message somebody will reword.
     */
    readonly codigo: string = "ErrorDeSolicitud",
  ) {
    super(`La API respondió ${status}: ${detalle}`);
    this.name = "ErrorDeApi";
  }
}

export interface OpcionesDeLlamada {
  readonly method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  readonly body?: unknown;
  readonly timeoutMs?: number;
  /** Off by default: a panel showing invoices must not serve a cached page. */
  readonly cache?: RequestCache;
}

function urlDelBackend(): string {
  const base = process.env.BACKEND_API_URL;
  if (base === undefined || base.trim() === "") {
    throw new Error("Falta BACKEND_API_URL. Copiá frontend/.env.example y completala.");
  }
  return base.replace(/\/$/, "");
}

export async function llamarApi<T>(ruta: string, opciones: OpcionesDeLlamada = {}): Promise<T> {
  const { method = "GET", body, timeoutMs = TIMEOUT_POR_DEFECTO_MS } = opciones;
  const token = leerToken();
  const control = new AbortController();
  const corte = setTimeout(() => control.abort(), timeoutMs);

  try {
    const respuesta = await fetch(`${urlDelBackend()}${ruta}`, {
      method,
      signal: control.signal,
      cache: opciones.cache ?? "no-store",
      headers: {
        "Content-Type": "application/json",
        ...(token !== undefined ? { Authorization: `Bearer ${token}` } : {}),
      },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });

    if (!respuesta.ok) {
      const { codigo, detalle } = await leerFalla(respuesta);
      throw new ErrorDeApi(respuesta.status, detalle, codigo);
    }
    return (await respuesta.json()) as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ErrorDeApi(504, `La API no respondió en ${timeoutMs} ms`);
    }
    throw error;
  } finally {
    clearTimeout(corte);
  }
}

interface Falla {
  readonly codigo: string;
  readonly detalle: string;
}

async function leerFalla(respuesta: Response): Promise<Falla> {
  try {
    const cuerpo: unknown = await respuesta.json();
    if (typeof cuerpo !== "object" || cuerpo === null) {
      return { codigo: "ErrorDeSolicitud", detalle: respuesta.statusText };
    }
    const detalle =
      "detalle" in cuerpo && typeof cuerpo.detalle === "string"
        ? cuerpo.detalle
        : respuesta.statusText;
    const codigo =
      "error" in cuerpo && typeof cuerpo.error === "string" ? cuerpo.error : "ErrorDeSolicitud";
    return { codigo, detalle };
  } catch {
    // A non-JSON body — an HTML error page from a proxy, most likely.
    return { codigo: "ErrorDeSolicitud", detalle: respuesta.statusText };
  }
}
