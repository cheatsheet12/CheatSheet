/**
 * BFF — el horario de atención y la política de fuera de horario (HS-T2 RN-04).
 *
 * `PUT` y no `POST` porque **reemplaza**: una empresa tiene un horario, no un catálogo.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function PUT(request: Request): Promise<NextResponse> {
  return reenviarAlBackend("/reglas/horario-de-atencion", "PUT", await cuerpoDe(request));
}
