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
 * Passes the backend's error *code* through, plus the detail when the status says the
 * detail is the answer.
 *
 * The code is what a form turns into Spanish copy. The `detalle` is forwarded on **422**
 * and nowhere else, because a 422 means "what you sent is wrong, and here is why" — the
 * explanation is the whole content of the response. On a 409 or a 403 the message is
 * written for a developer reading a log, and the browser is not that reader.
 *
 * **This used to test the code for the exact string `EntradaInvalida`**, which silently
 * dropped the message of every subclass. `spreadsheet_sync` has four of them, and
 * HU-E3-03 states its rejections word for word — «Formato no aceptado. Use .xlsx, .xls o
 * .csv.» — so the acceptance criteria depend on the text arriving. Matching on the status
 * instead of on one class name is what makes that true for the next subclass too, without
 * anybody having to remember to widen a list.
 *
 * It does **not** fix `ClienteDuplicado` (`TODO.md` §10): that one is an
 * `InvarianteViolada` and answers 409, so its message is still dropped here. Whether it
 * should become a 422 is epic 3's call, not this one's.
 */
export function respuestaDeError(error: ErrorDeApi | null): NextResponse {
  if (error === null) {
    return NextResponse.json({ error: "ErrorInterno" }, { status: 500 });
  }
  const cuerpo =
    error.status === 422 ? { error: error.codigo, detalle: error.detalle } : { error: error.codigo };
  return NextResponse.json(cuerpo, { status: error.status });
}
