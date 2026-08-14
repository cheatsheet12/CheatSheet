/**
 * BFF — step 2 of the onboarding (HU-E1-02).
 *
 * Unlike the other three this one needs a session: the backend resolves the company from
 * the access token, and `llamarApi` attaches it from the HttpOnly cookie.
 */

import { NextResponse } from "next/server";

import { ErrorDeApi, llamarApi } from "@/lib/api";
import { haySesion } from "@/lib/session";

import { respuestaDeError } from "@/app/api/auth/_sesion";

export const dynamic = "force-dynamic";

interface RespuestaDeEmpresa {
  readonly onboarding_completo: boolean;
}

export async function PUT(request: Request): Promise<NextResponse> {
  if (!haySesion()) {
    return NextResponse.json({ error: "NoAutenticado" }, { status: 401 });
  }
  const cuerpo: unknown = await request.json();
  try {
    const resultado = await llamarApi<RespuestaDeEmpresa>("/auth/empresa", {
      method: "PUT",
      body: cuerpo,
    });
    return NextResponse.json(resultado);
  } catch (error) {
    return respuestaDeError(error instanceof ErrorDeApi ? error : null);
  }
}
