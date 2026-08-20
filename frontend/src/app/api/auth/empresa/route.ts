/**
 * BFF — the company's fiscal data (HU-E1-02).
 *
 * Unlike the other three this one needs a session: the backend resolves the company from
 * the access token, and `llamarApi` attaches it from the HttpOnly cookie.
 *
 * `GET` was added by `padron-y-datos-fiscales`: the edit screen has to load the current
 * values into its form, and a form cannot show what the BFF does not forward.
 */

import { NextResponse } from "next/server";

import { ErrorDeApi, llamarApi } from "@/lib/api";
import { haySesion } from "@/lib/session";

import { respuestaDeError } from "@/app/api/auth/_sesion";

export const dynamic = "force-dynamic";

interface RespuestaDeEmpresa {
  readonly onboarding_completo: boolean;
}

export async function GET(): Promise<NextResponse> {
  if (!haySesion()) {
    return NextResponse.json({ error: "NoAutenticado" }, { status: 401 });
  }
  try {
    return NextResponse.json(await llamarApi<unknown>("/auth/empresa"));
  } catch (error) {
    return respuestaDeError(error instanceof ErrorDeApi ? error : null);
  }
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
