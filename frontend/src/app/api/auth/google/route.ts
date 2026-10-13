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
 * **The consent rides along, by POST only** (HU-E1-08 RN-03). The sign-up form posts the
 * versions of the terms and the policy that were ticked as `terminos` and `privacidad`;
 * they are kept in a second HttpOnly cookie, with the same lifetime and scope as `state`,
 * because Google's round trip drops everything else. The callback forwards them to the
 * API, which decides whether they are the versions in force — nothing here is trusted.
 *
 * A GET never records consent: a link is not a tick, and a crafted one would otherwise
 * register acceptances nobody gave. Signing in (GET) leaves no cookie and removes a stale
 * one. A POST that does not come from our own origin is treated as sign-in too.
 */

import { randomUUID } from "node:crypto";

import { NextResponse } from "next/server";

import { borrarCookieDeOAuth, guardarCookieDeOAuth } from "@/app/api/auth/_oauth";
import { ErrorDeApi, llamarApi } from "@/lib/api";

export const dynamic = "force-dynamic";

export const COOKIE_STATE = "cheatsheet_oauth_state";
export const COOKIE_CONSENTIMIENTO = "cheatsheet_oauth_consentimiento";
/** `N.N`, at most 20 characters: the same shape the API accepts for a version. */
const FORMATO_DE_VERSION = /^\d+\.\d+$/;
const LARGO_MAXIMO_DE_VERSION = 20;

interface RespuestaDeUrl {
  readonly url: string;
}

interface ConsentimientoDeFormulario {
  readonly terminos: string;
  readonly privacidad: string;
}

function esVersion(valor: FormDataEntryValue | null): valor is string {
  return (
    typeof valor === "string" &&
    valor.length <= LARGO_MAXIMO_DE_VERSION &&
    FORMATO_DE_VERSION.test(valor)
  );
}

/** A browser form from our own origin; one that names another origin is somebody else's. */
function esDeNuestroOrigen(request: Request): boolean {
  const origen = request.headers.get("origin");
  return origen === null || origen === new URL(urlDeLaApp()).origin;
}

async function leerConsentimiento(request: Request): Promise<ConsentimientoDeFormulario | null> {
  if (!esDeNuestroOrigen(request)) {
    return null;
  }
  try {
    const formulario = await request.formData();
    const terminos = formulario.get("terminos");
    const privacidad = formulario.get("privacidad");
    return esVersion(terminos) && esVersion(privacidad) ? { terminos, privacidad } : null;
  } catch {
    // Not a form body: treated as "no consent", and the API refuses a new account without it.
    return null;
  }
}

/** Keep the consent for the callback, or forget any left over from an earlier attempt. */
function guardarConsentimiento(consentimiento: ConsentimientoDeFormulario | null): void {
  if (consentimiento === null) {
    borrarCookieDeOAuth(COOKIE_CONSENTIMIENTO);
    return;
  }
  guardarCookieDeOAuth(
    COOKIE_CONSENTIMIENTO,
    JSON.stringify({
      version_terminos: consentimiento.terminos,
      version_privacidad: consentimiento.privacidad,
    }),
  );
}

async function iniciarFlujo(
  consentimiento: ConsentimientoDeFormulario | null,
  status: 307 | 303,
): Promise<NextResponse> {
  const state = randomUUID();
  try {
    const { url } = await llamarApi<RespuestaDeUrl>(
      `/auth/google/url?state=${encodeURIComponent(state)}`,
    );
    guardarCookieDeOAuth(COOKIE_STATE, state);
    guardarConsentimiento(consentimiento);
    return NextResponse.redirect(url, status);
  } catch (error) {
    const detalle = error instanceof ErrorDeApi ? error.codigo : "ErrorInterno";
    return NextResponse.redirect(new URL(`/?error=${detalle}`, urlDeLaApp()), status);
  }
}

/** Sign in with an existing account: no consent is asked for, none is recorded. */
export async function GET(_request: Request): Promise<NextResponse> {
  return iniciarFlujo(null, 307);
}

/** Sign up: the form carries the two ticked versions. 303 so Google is reached with a GET. */
export async function POST(request: Request): Promise<NextResponse> {
  return iniciarFlujo(await leerConsentimiento(request), 303);
}

export function urlDeLaApp(): string {
  return process.env.APP_BASE_URL ?? "http://localhost:3000";
}
