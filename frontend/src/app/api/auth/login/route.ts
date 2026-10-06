/**
 * BFF — sign in. See `../registro/route.ts` for why the tokens stop here.
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
    const sesion = await llamarApi<RespuestaDeSesion>("/auth/login", {
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
