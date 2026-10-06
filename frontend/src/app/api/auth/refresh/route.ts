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

import { renovarSesion } from "@/app/api/auth/_sesion";

export const dynamic = "force-dynamic";

export async function POST(): Promise<NextResponse> {
  const resultado = await renovarSesion();
  switch (resultado.tipo) {
    case "renovada":
      return NextResponse.json({ onboarding_completo: resultado.onboardingCompleto });
    case "caida":
      return NextResponse.json({ error: "SesionInvalida" }, { status: 502 });
    case "sin-refresh":
    case "rechazada":
      return NextResponse.json({ error: "SesionInvalida" }, { status: 401 });
  }
}
