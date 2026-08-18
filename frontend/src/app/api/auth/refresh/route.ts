/**
 * BFF — renew the session (ADR-011).
 *
 * **The debt this pays.** Without it the panel simply died fifteen minutes after signing
 * in, because the access cookie expired and nothing renewed it.
 *
 * The refresh token is read from its own HttpOnly cookie and never from the request
 * body: a body is something a page can be tricked into sending, and this token mints
 * access tokens for days.
 *
 * **A rejected rotation clears both cookies.** The backend treats a reused token as
 * theft and revokes the whole family; leaving the browser holding a dead one would loop
 * it through this endpoint on every request.
 */

import { NextResponse } from "next/server";

import { ErrorDeApi, llamarApi } from "@/lib/api";
import { cerrarSesion, guardarSesion } from "@/lib/session";

import type { RespuestaDeSesion } from "@/app/api/auth/_sesion";
import { borrarRefresh, guardarRefresh, leerRefresh } from "@/app/api/auth/_sesion";

export const dynamic = "force-dynamic";

export async function POST(): Promise<NextResponse> {
  const refresh = leerRefresh();
  if (refresh === undefined) {
    return NextResponse.json({ error: "SesionInvalida" }, { status: 401 });
  }
  try {
    const sesion = await llamarApi<RespuestaDeSesion>("/auth/refresh", {
      method: "POST",
      body: { refresh_token: refresh },
    });
    guardarSesion({ token: sesion.access_token });
    guardarRefresh(sesion.refresh_token);
    return NextResponse.json({ onboarding_completo: sesion.onboarding_completo });
  } catch (error) {
    cerrarSesion();
    borrarRefresh();
    const status = error instanceof ErrorDeApi && error.status < 500 ? 401 : 502;
    return NextResponse.json({ error: "SesionInvalida" }, { status });
  }
}
