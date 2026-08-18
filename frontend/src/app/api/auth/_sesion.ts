/**
 * Shared plumbing for the auth route handlers.
 *
 * The underscore keeps it out of Next's routing: files starting with `_` are not routes.
 *
 * **The refresh token gets its own cookie, scoped to `/api/auth`.** It is long-lived and
 * powerful — anything holding it can mint access tokens for days — so it is not sent on
 * every request to every path the way the access cookie is. `SameSite=Strict` on this
 * one, because no legitimate flow refreshes a session from a cross-site navigation.
 */

import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import type { ErrorDeApi } from "@/lib/api";

export const REFRESH_COOKIE_NAME = "cheatsheet_refresh";
const MAX_AGE_REFRESH = 30 * 24 * 60 * 60;

export interface RespuestaDeSesion {
  readonly access_token: string;
  readonly refresh_token: string;
  readonly empresa_id: string;
  readonly usuario_id: string;
  readonly onboarding_completo: boolean;
}

export function guardarRefresh(token: string): void {
  cookies().set({
    name: REFRESH_COOKIE_NAME,
    value: token,
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/api/auth",
    maxAge: MAX_AGE_REFRESH,
  });
}

export function leerRefresh(): string | undefined {
  return cookies().get(REFRESH_COOKIE_NAME)?.value;
}

export function borrarRefresh(): void {
  cookies().delete(REFRESH_COOKIE_NAME);
}

/**
 * Passes the backend's error *code* through, and nothing else.
 *
 * The code is what the form turns into Spanish copy. The `detalle` is forwarded only for
 * validation errors: it is written for a developer reading a log, and the browser is not
 * that reader.
 */
export function respuestaDeError(error: ErrorDeApi | null): NextResponse {
  if (error === null) {
    return NextResponse.json({ error: "ErrorInterno" }, { status: 500 });
  }
  const cuerpo =
    error.codigo === "EntradaInvalida"
      ? { error: error.codigo, detalle: error.detalle }
      : { error: error.codigo };
  return NextResponse.json(cuerpo, { status: error.status });
}
