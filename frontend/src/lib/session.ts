/**
 * The session cookie.
 *
 * The access token lives in an **HttpOnly** cookie set by this BFF, so JavaScript in
 * the browser cannot read it (ADR-011). That is the whole reason the BFF exists: a
 * token in `localStorage` is a token that any injected script can exfiltrate, and an
 * admin panel that issues tax documents is not the place to find that out.
 *
 * Every function here runs on the server. Importing this module from a Client
 * Component is a build error, which is the intended guard rail.
 */

import { cookies } from "next/headers";

export const SESSION_COOKIE_NAME = process.env.SESSION_COOKIE_NAME ?? "cheatsheet_session";

/** Lifetime of the access cookie. Short by design: the refresh token renews it. */
const MAX_AGE_SEGUNDOS = 15 * 60;

export interface OpcionesDeSesion {
  readonly token: string;
  readonly maxAge?: number;
}

export function leerToken(): string | undefined {
  return cookies().get(SESSION_COOKIE_NAME)?.value;
}

export function haySesion(): boolean {
  return leerToken() !== undefined;
}

export function guardarSesion({ token, maxAge }: OpcionesDeSesion): void {
  cookies().set({
    name: SESSION_COOKIE_NAME,
    value: token,
    httpOnly: true,
    // Off in local development only: cookies marked Secure are dropped over http://.
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: maxAge ?? MAX_AGE_SEGUNDOS,
  });
}

export function cerrarSesion(): void {
  cookies().delete(SESSION_COOKIE_NAME);
}

/** What the access token carries. Mirrors the claims `EmisorDeTokensJWT` writes. */
export interface ClaimsDeSesion {
  readonly usuarioId: string;
  readonly empresaId: string;
  readonly rol: string;
}

/**
 * Read the claims of the access cookie **without verifying the signature**.
 *
 * That sounds alarming, so here is why it is not: this cookie is written by this server,
 * is HttpOnly, and is never touched by anything in the browser. And nothing here is a
 * security decision — the claims are used to decide which buttons to render. Every
 * decision that matters is made by the backend, which *does* verify the signature, on
 * every single request.
 *
 * Verifying here would mean shipping the JWT secret into the Next process, which is a
 * second copy of the most sensitive value in the system in exchange for nothing.
 *
 * Returns `null` for a missing or malformed cookie: the caller treats that as no session,
 * which is what it is.
 */
export function leerClaims(): ClaimsDeSesion | null {
  const token = leerToken();
  if (token === undefined) {
    return null;
  }
  const partes = token.split(".");
  if (partes.length !== 3 || partes[1] === undefined) {
    return null;
  }
  try {
    const cuerpo: unknown = JSON.parse(Buffer.from(partes[1], "base64url").toString("utf8"));
    if (typeof cuerpo !== "object" || cuerpo === null) {
      return null;
    }
    const leer = (clave: string): string =>
      clave in cuerpo ? String((cuerpo as Record<string, unknown>)[clave]) : "";
    const claims = { usuarioId: leer("sub"), empresaId: leer("empresa_id"), rol: leer("rol") };
    return claims.usuarioId === "" || claims.empresaId === "" ? null : claims;
  } catch {
    return null;
  }
}
