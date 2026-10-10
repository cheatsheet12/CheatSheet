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
 * The consent cookie left by the first leg (HU-E1-08 RN-03) is read and deleted at the
 * top, whatever happens next: it is single use, like `state`. It is forwarded to the API,
 * which refuses to create a new account without it — an existing account signs in without.
 *
 * The session cookies are set exactly as sign-in sets them, and the browser is sent to
 * the panel or to step 2 of the onboarding depending on what the company still owes.
 */

import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { ErrorDeApi, llamarApi } from "@/lib/api";
import { guardarSesion } from "@/lib/session";

import { borrarCookieDeOAuth } from "@/app/api/auth/_oauth";
import type { RespuestaDeSesion } from "@/app/api/auth/_sesion";
import { guardarRefresh } from "@/app/api/auth/_sesion";
import { COOKIE_CONSENTIMIENTO, COOKIE_STATE, urlDeLaApp } from "@/app/api/auth/google/route";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<NextResponse> {
  const parametros = new URL(request.url).searchParams;
  const esperado = cookies().get(COOKIE_STATE)?.value;
  borrarCookieDeOAuth(COOKIE_STATE);
  const consentimiento = leerConsentimiento();

  const problema = validar(parametros, esperado);
  if (problema !== null) {
    return NextResponse.redirect(new URL(`/?error=${problema}`, urlDeLaApp()));
  }

  try {
    const sesion = await llamarApi<RespuestaDeSesion>("/auth/google/callback", {
      method: "POST",
      body: {
        codigo: parametros.get("code"),
        ...(consentimiento !== null ? { consentimiento } : {}),
      },
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

interface Consentimiento {
  readonly version_terminos: string;
  readonly version_privacidad: string;
}

/** Read and delete. An unreadable cookie is treated as absent: the API then decides. */
function leerConsentimiento(): Consentimiento | null {
  const crudo = cookies().get(COOKIE_CONSENTIMIENTO)?.value;
  borrarCookieDeOAuth(COOKIE_CONSENTIMIENTO);
  if (crudo === undefined) {
    return null;
  }
  try {
    const valor: unknown = JSON.parse(crudo);
    if (
      typeof valor === "object" &&
      valor !== null &&
      "version_terminos" in valor &&
      typeof valor.version_terminos === "string" &&
      "version_privacidad" in valor &&
      typeof valor.version_privacidad === "string"
    ) {
      return {
        version_terminos: valor.version_terminos,
        version_privacidad: valor.version_privacidad,
      };
    }
  } catch {
    // Not JSON: somebody edited the cookie. Falls through to "no consent".
  }
  return null;
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
