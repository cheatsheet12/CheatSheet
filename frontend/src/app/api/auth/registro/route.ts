/**
 * BFF — sign up.
 *
 * This is where the tokens stop. The backend answers with an access token and a refresh
 * token in the body; this handler puts them in HttpOnly cookies and returns to the
 * browser only what the screen needs to decide where to go next. A token that never
 * reaches the bundle is a token no injected script can read (ADR-011).
 */

import { NextResponse } from "next/server";

import { ErrorDeApi, llamarApi } from "@/lib/api";
import { guardarSesion } from "@/lib/session";

import type { RespuestaDeSesion } from "@/app/api/auth/_sesion";
import { guardarRefresh, respuestaDeError } from "@/app/api/auth/_sesion";

export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<NextResponse> {
  const cuerpo: unknown = await request.json();
  try {
    const sesion = await llamarApi<RespuestaDeSesion>("/auth/registro", {
      method: "POST",
      body: cuerpo,
    });
    guardarSesion({ token: sesion.access_token });
    guardarRefresh(sesion.refresh_token);
    return NextResponse.json({ onboarding_completo: sesion.onboarding_completo });
  } catch (error) {
    return respuestaDeError(error instanceof ErrorDeApi ? error : null);
  }
}
