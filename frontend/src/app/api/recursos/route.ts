/**
 * BFF — los recursos reservables de la empresa (PAN-AGE-03).
 *
 * **No hay `DELETE`.** HU-E7-04 RN-03 pide desactivar: un recurso borrado dejaría los turnos
 * que se prestaron en él apuntando a algo que ya no existe.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<NextResponse> {
  const consulta = new URL(request.url).search;
  return reenviarAlBackend(`/recursos${consulta}`, "GET");
}

export async function POST(request: Request): Promise<NextResponse> {
  return reenviarAlBackend("/recursos", "POST", await cuerpoDe(request));
}
