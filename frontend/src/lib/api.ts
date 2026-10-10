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

import { AsyncLocalStorage } from "node:async_hooks";

import { redirect } from "next/navigation";

import { leerToken } from "@/lib/session";

const TIMEOUT_POR_DEFECTO_MS = 10_000;

/** What the API answers (403) to every call while a legal document is pending. */
const CODIGO_DE_BLOQUEO_LEGAL = "AceptacionLegalPendiente";
const RUTA_DE_ACEPTACION_LEGAL = "/aceptacion-legal";

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
  /**
   * For **public pages that must not fail** (HU-E1-03 RN-05): Next caches the response and
   * revalidates it at most this often, and if the backend is down when it does, it keeps
   * serving the last good copy. Replaces `cache` — the two are mutually exclusive, and
   * everything else keeps the `no-store` default.
   */
  readonly revalidarCadaSegundos?: number;
  /**
   * Cabeceras extra para el backend. Existe por pocos casos y conviene que siga así (el
   * `X-Idempotency-Key` de un pedido con efecto externo, ADR-0013, es el segundo): el
   * `state` del ida y vuelta con Google viaja en una cookie que el backend vuelve a
   * verificar, y el BFF es el único que la ve. Sin esto, ese guarda no se puede satisfacer
   * desde el panel — que es el único camino, porque el navegador nunca habla con la API.
   */
  readonly headers?: Readonly<Record<string, string>>;
}

/**
 * Who is asking decides what a `403 AceptacionLegalPendiente` becomes (HU-E1-03 RN-03,
 * HU-E1-08 RN-05).
 *
 * - **A server page redirects to `/aceptacion-legal`, by default.** A soft (client-side)
 *   navigation does not re-run the panel layout, so the layout's own check cannot catch a
 *   version that took effect meanwhile; redirecting inside `llamarApi` means no page, present
 *   or future, has to remember to.
 * - **A BFF route handler must keep the JSON 403**: its caller is the browser, and
 *   `VigilanteDeAceptacionLegal` reads that body. A redirect thrown inside a handler would
 *   answer a `307` to a `fetch` instead. Handlers run their backend call through
 *   `comoRutaDelBff`.
 *
 * It is an `AsyncLocalStorage` rather than an option on `OpcionesDeLlamada` so the proxy that
 * most handlers share can set it once, without changing a single argument its callers send.
 */
const contextoDelBff = new AsyncLocalStorage<true>();

export function comoRutaDelBff<T>(trabajo: () => Promise<T>): Promise<T> {
  return contextoDelBff.run(true, trabajo);
}

function alBloqueoLegal(status: number, codigo: string): void {
  if (status === 403 && codigo === CODIGO_DE_BLOQUEO_LEGAL && contextoDelBff.getStore() !== true) {
    redirect(RUTA_DE_ACEPTACION_LEGAL);
  }
}

function urlDelBackend(): string {
  const base = process.env.BACKEND_API_URL;
  if (base === undefined || base.trim() === "") {
    throw new Error("Falta BACKEND_API_URL. Copiá frontend/.env.example y completala.");
  }
  return base.replace(/\/$/, "");
}

/**
 * Call the backend and return the JSON body as `T`.
 *
 * A successful response with **no body** — a `204 No Content`, which is what every DELETE
 * of the API answers — resolves to `undefined`, not to an error. Whoever calls a 204
 * endpoint declares `T` as `unknown` or `undefined`: the `undefined as T` is the same
 * contract assertion the `as T` on the parsed JSON already is. A 200 whose body is
 * present but not valid JSON still throws `SyntaxError`; it is not hidden.
 */
export async function llamarApi<T>(ruta: string, opciones: OpcionesDeLlamada = {}): Promise<T> {
  const { method = "GET", body, timeoutMs = TIMEOUT_POR_DEFECTO_MS } = opciones;
  const token = leerToken();
  const control = new AbortController();
  const corte = setTimeout(() => control.abort(), timeoutMs);

  try {
    const respuesta = await fetch(`${urlDelBackend()}${ruta}`, {
      method,
      signal: control.signal,
      ...(opciones.revalidarCadaSegundos !== undefined
        ? { next: { revalidate: opciones.revalidarCadaSegundos } }
        : { cache: opciones.cache ?? "no-store" }),
      headers: {
        "Content-Type": "application/json",
        ...(token !== undefined ? { Authorization: `Bearer ${token}` } : {}),
        ...(opciones.headers ?? {}),
      },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });

    if (!respuesta.ok) {
      const { codigo, detalle } = await leerFalla(respuesta);
      alBloqueoLegal(respuesta.status, codigo);
      throw new ErrorDeApi(respuesta.status, detalle, codigo);
    }
    const texto = await respuesta.text();
    if (texto === "") {
      return undefined as T;
    }
    return JSON.parse(texto) as T;
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

/** How long an upload may take. A 25 MB workbook over a slow uplink is not 10 seconds. */
const TIMEOUT_DE_SUBIDA_MS = 120_000;

/**
 * Send raw bytes to the backend — the spreadsheet upload of HU-E3-03, and nothing else so
 * far.
 *
 * A separate function rather than an option on `llamarApi`, because everything about it
 * differs: the body is not serialised, the content type is not JSON, and the timeout is
 * twelve times longer. Folding those into the JSON path would mean three conditionals in
 * the function every other call in the app goes through.
 */
export async function subirBinario<T>(
  ruta: string,
  contenido: ArrayBuffer,
  opciones: { readonly timeoutMs?: number } = {},
): Promise<T> {
  const { timeoutMs = TIMEOUT_DE_SUBIDA_MS } = opciones;
  const token = leerToken();
  const control = new AbortController();
  const corte = setTimeout(() => control.abort(), timeoutMs);

  try {
    const respuesta = await fetch(`${urlDelBackend()}${ruta}`, {
      method: "POST",
      signal: control.signal,
      cache: "no-store",
      headers: {
        "Content-Type": "application/octet-stream",
        ...(token !== undefined ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: contenido,
    });

    if (!respuesta.ok) {
      const { codigo, detalle } = await leerFalla(respuesta);
      throw new ErrorDeApi(respuesta.status, detalle, codigo);
    }
    return (await respuesta.json()) as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ErrorDeApi(504, `La subida no termino en ${timeoutMs} ms`);
    }
    throw error;
  } finally {
    clearTimeout(corte);
  }
}

/** What a binary download answers: the bytes, and how to name them. */
export interface ArchivoDescargado {
  readonly contenido: ArrayBuffer;
  readonly tipo: string;
  readonly disposicion: string;
}

/**
 * Fetch bytes rather than JSON — the counterpart of `subirBinario`.
 *
 * It exists for exactly the reason that one does: `llamarApi` parses the response as JSON,
 * and a PDF fails on its first byte. Everything else is shared with it deliberately — the
 * bearer token, the timeout, and the error translation — because those are the three things
 * a route that rolled its own `fetch` would get subtly wrong.
 *
 * **A failure is still JSON**, so it goes through `leerFalla` like every other call: on a
 * 422 that carries the backend's own sentence, which is what the screen shows instead of an
 * empty tab.
 */
export async function descargarBinario(
  ruta: string,
  opciones: { readonly timeoutMs?: number } = {},
): Promise<ArchivoDescargado> {
  const { timeoutMs = TIMEOUT_POR_DEFECTO_MS } = opciones;
  const token = leerToken();
  const control = new AbortController();
  const corte = setTimeout(() => control.abort(), timeoutMs);

  try {
    const respuesta = await fetch(`${urlDelBackend()}${ruta}`, {
      method: "GET",
      signal: control.signal,
      cache: "no-store",
      headers: token !== undefined ? { Authorization: `Bearer ${token}` } : {},
    });

    if (!respuesta.ok) {
      const { codigo, detalle } = await leerFalla(respuesta);
      throw new ErrorDeApi(respuesta.status, detalle, codigo);
    }
    return {
      contenido: await respuesta.arrayBuffer(),
      tipo: respuesta.headers.get("Content-Type") ?? "application/octet-stream",
      disposicion: respuesta.headers.get("Content-Disposition") ?? "inline",
    };
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ErrorDeApi(504, `La descarga no termino en ${timeoutMs} ms`);
    }
    throw error;
  } finally {
    clearTimeout(corte);
  }
}
