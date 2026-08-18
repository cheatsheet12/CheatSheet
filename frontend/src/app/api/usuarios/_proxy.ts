/**
 * Shared plumbing for the user-administration route handlers.
 *
 * Every one of them does the same three things: refuse without a session, forward to the
 * backend with the bearer token from the HttpOnly cookie, and translate a failure into a
 * body carrying the error *code* and nothing else. Writing that seven times is writing
 * six chances to forget the first step.
 *
 * The underscore keeps the file out of Next's routing.
 */

import { NextResponse } from "next/server";

import { ErrorDeApi, llamarApi } from "@/lib/api";
import { haySesion } from "@/lib/session";

import { respuestaDeError } from "@/app/api/auth/_sesion";

export type Metodo = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export async function reenviarAlBackend(
  ruta: string,
  metodo: Metodo,
  cuerpo?: unknown,
): Promise<NextResponse> {
  if (!haySesion()) {
    return NextResponse.json({ error: "NoAutenticado" }, { status: 401 });
  }
  try {
    const datos = await llamarApi<unknown>(ruta, {
      method: metodo,
      ...(cuerpo !== undefined ? { body: cuerpo } : {}),
    });
    return NextResponse.json(datos ?? {});
  } catch (error) {
    return respuestaDeError(error instanceof ErrorDeApi ? error : null);
  }
}

/** The body of a request that may legitimately have none. */
export async function cuerpoDe(request: Request): Promise<unknown> {
  try {
    return await request.json();
  } catch {
    return {};
  }
}
