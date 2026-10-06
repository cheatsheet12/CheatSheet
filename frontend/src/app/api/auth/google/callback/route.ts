/**
 * BFF — come back from Google with an authorization code (HU-E1-01 RN-02).
 *
 * Three checks before anything happens, in this order:
 *
 * 1. `state` matches the cookie minted when the flow started. A mismatch is a forged
 *    callback and the request stops here, before the code is spent.
 * 2. Google did not send an `error` instead of a code — someone who pressed "cancel"
 *    lands here too, and that is not a failure to report as one.
 * 3. There is a code at all.
 *
 * The session cookies are set exactly as sign-in sets them, and the browser is sent to
 * the panel or to step 2 of the onboarding depending on what the company still owes.
 */

import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { ErrorDeApi, llamarApi } from "@/lib/api";
import { guardarSesion } from "@/lib/session";

import type { RespuestaDeSesion } from "@/app/api/auth/_sesion";
import { guardarRefresh } from "@/app/api/auth/_sesion";
import { COOKIE_STATE, urlDeLaApp } from "@/app/api/auth/google/route";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<NextResponse> {
  const parametros = new URL(request.url).searchParams;
  const esperado = cookies().get(COOKIE_STATE)?.value;
  cookies().delete(COOKIE_STATE);

  const problema = validar(parametros, esperado);
  if (problema !== null) {
    return NextResponse.redirect(new URL(`/?error=${problema}`, urlDeLaApp()));
  }

  try {
    const sesion = await llamarApi<RespuestaDeSesion>("/auth/google/callback", {
      method: "POST",
      body: { codigo: parametros.get("code") },
    });
    guardarSesion({ token: sesion.access_token });
    guardarRefresh(sesion.refresh_token);
    return NextResponse.redirect(
      new URL(sesion.onboarding_completo ? "/panel" : "/onboarding/empresa", urlDeLaApp()),
    );
  } catch (error) {
    const codigo = error instanceof ErrorDeApi ? error.codigo : "ErrorInterno";
    return NextResponse.redirect(new URL(`/?error=${codigo}`, urlDeLaApp()));
  }
}

function validar(parametros: URLSearchParams, esperado: string | undefined): string | null {
  if (parametros.get("error") !== null) {
    return "OAuthCancelado";
  }
  const state = parametros.get("state");
  if (esperado === undefined || state === null || state !== esperado) {
    return "OAuthStateInvalido";
  }
  return parametros.get("code") === null ? "OAuthFallido" : null;
}
