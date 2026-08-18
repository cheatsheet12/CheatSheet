/**
 * Shared plumbing for the integration route handlers.
 *
 * Same three obligations as the user-administration proxy: refuse without a session,
 * forward with the bearer token from the HttpOnly cookie, and translate a failure into a
 * body carrying the error code and nothing else.
 *
 * The underscore keeps the file out of Next's routing.
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";
import type { Metodo } from "@/app/api/usuarios/_proxy";

export async function reenviarIntegracion(
  ruta: string,
  metodo: Metodo,
  cuerpo?: unknown,
): Promise<NextResponse> {
  return reenviarAlBackend(ruta, metodo, cuerpo);
}
