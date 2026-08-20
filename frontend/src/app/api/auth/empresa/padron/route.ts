/**
 * BFF — «Validar contra ARCA» (HU-E1-02 RN-01 y RN-02).
 *
 * A `POST` on what is really a read. The body carries a CUIT, which is somebody's tax id:
 * in a query string it would be written to every access log on the way and left in the
 * browser's history.
 *
 * The three outcomes travel through untouched. Turning «no encontrado» and «no disponible»
 * into one flag here would undo the distinction the whole unit is built on.
 */

import { NextResponse } from "next/server";

import { ErrorDeApi, llamarApi } from "@/lib/api";
import { haySesion } from "@/lib/session";

import { respuestaDeError } from "@/app/api/auth/_sesion";

export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<NextResponse> {
  if (!haySesion()) {
    return NextResponse.json({ error: "NoAutenticado" }, { status: 401 });
  }
  const cuerpo: unknown = await request.json();
  try {
    const resultado = await llamarApi<unknown>("/auth/empresa/padron", {
      method: "POST",
      body: cuerpo,
    });
    return NextResponse.json(resultado);
  } catch (error) {
    return respuestaDeError(error instanceof ErrorDeApi ? error : null);
  }
}
