/**
 * BFF — start the Google flow (HU-E1-01 RN-02).
 *
 * **The debt this pays.** PAN-ONB-01 has linked here since the previous unit and nothing
 * answered.
 *
 * `state` is minted here, stored in a short-lived HttpOnly cookie and checked on the way
 * back. It is the CSRF defence of the OAuth flow: without it, anybody can send a victim
 * a callback URL carrying *their* authorization code and quietly attach the victim's
 * browser to the attacker's account.
 *
 * **The consent rides along** (HU-E1-08 RN-03). The sign-up form sends the versions of the
 * terms and the policy that were ticked as `?terminos=&privacidad=`; they are kept in a
 * second HttpOnly cookie, with the same lifetime and scope as `state`, because Google's
 * round trip drops everything else. The callback forwards them to the API, which decides
 * whether they are the versions in force — nothing here is trusted. Without them (an
 * existing user signing in) no cookie is written and a stale one is removed.
 */

import { randomUUID } from "node:crypto";

import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { ErrorDeApi, llamarApi } from "@/lib/api";

export const dynamic = "force-dynamic";

export const COOKIE_STATE = "cheatsheet_oauth_state";
export const COOKIE_CONSENTIMIENTO = "cheatsheet_oauth_consentimiento";
const VIDA_DEL_STATE = 10 * 60;
/** `N.N`, at most 20 characters: the same shape the API accepts for a version. */
const FORMATO_DE_VERSION = /^\d+\.\d+$/;
const LARGO_MAXIMO_DE_VERSION = 20;

interface RespuestaDeUrl {
  readonly url: string;
}

function esVersion(valor: string | null): valor is string {
  return (
    valor !== null && valor.length <= LARGO_MAXIMO_DE_VERSION && FORMATO_DE_VERSION.test(valor)
  );
}

/** Keep the consent for the callback, or forget any left over from an earlier attempt. */
function guardarConsentimiento(parametros: URLSearchParams): void {
  const terminos = parametros.get("terminos");
  const privacidad = parametros.get("privacidad");
  if (!esVersion(terminos) || !esVersion(privacidad)) {
    cookies().delete(COOKIE_CONSENTIMIENTO);
    return;
  }
  cookies().set({
    name: COOKIE_CONSENTIMIENTO,
    value: JSON.stringify({ version_terminos: terminos, version_privacidad: privacidad }),
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/api/auth",
    maxAge: VIDA_DEL_STATE,
  });
}

export async function GET(request: Request): Promise<NextResponse> {
  const state = randomUUID();
  const parametros = new URL(request.url).searchParams;
  try {
    const { url } = await llamarApi<RespuestaDeUrl>(
      `/auth/google/url?state=${encodeURIComponent(state)}`,
    );
    cookies().set({
      name: COOKIE_STATE,
      value: state,
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      // `lax`, not `strict`: the browser arrives back here from Google's domain, and a
      // strict cookie would not be sent on that navigation.
      sameSite: "lax",
      path: "/api/auth",
      maxAge: VIDA_DEL_STATE,
    });
    guardarConsentimiento(parametros);
    return NextResponse.redirect(url);
  } catch (error) {
    const detalle = error instanceof ErrorDeApi ? error.codigo : "ErrorInterno";
    return NextResponse.redirect(new URL(`/?error=${detalle}`, urlDeLaApp()));
  }
}

export function urlDeLaApp(): string {
  return process.env.APP_BASE_URL ?? "http://localhost:3000";
}
