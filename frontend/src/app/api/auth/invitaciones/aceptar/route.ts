/**
 * BFF — accept an invitation (HU-E1-04 RN-02).
 *
 * Public, like sign-up and sign-in: whoever calls has no session, and getting one is
 * exactly what accepting does. The tokens stop here, in HttpOnly cookies, and the
 * browser never sees either of them.
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
    const sesion = await llamarApi<RespuestaDeSesion>("/auth/invitaciones/aceptar", {
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
