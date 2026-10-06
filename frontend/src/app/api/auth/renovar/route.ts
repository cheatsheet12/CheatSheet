/**
 * BFF — renew the session on a page navigation, then continue.
 *
 * The panel layout sends a navigation here when the access cookie is gone. It has to be a
 * route under `/api/auth`: the refresh cookie is scoped to that path, so a page of the
 * panel never sees it.
 *
 * **It answers a GET and still mutates cookies**, which is safe here for one reason: the
 * refresh cookie is `SameSite=Strict`. A link from another site arrives without it, the
 * renewal finds nothing, and the visitor lands on the login like any stranger.
 *
 * `destino` only accepts a path of this site. Anything else — another origin, `//host`,
 * a backslash trick — is replaced by the panel's home, or this becomes an open redirect.
 */

import { NextResponse } from "next/server";

import { destinoSeguro, renovarSesion } from "@/app/api/auth/_sesion";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<NextResponse> {
  const url = new URL(request.url);
  const resultado = await renovarSesion();
  if (resultado.tipo !== "renovada") {
    return NextResponse.redirect(new URL("/", url));
  }
  if (!resultado.onboardingCompleto) {
    return NextResponse.redirect(new URL("/onboarding/empresa", url));
  }
  return NextResponse.redirect(new URL(destinoSeguro(url.searchParams.get("destino")), url));
}
