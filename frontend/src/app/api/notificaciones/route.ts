/**
 * BFF — el centro de notificaciones (PAN-CFG-NOT, HU-E11-03).
 *
 * **No lleva id de usuario.** El destinatario sale de la sesión del lado del backend: no hay
 * forma de pedir la bandeja de otra persona, ni siquiera equivocándose.
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<NextResponse> {
  const consulta = new URL(request.url).search;
  return reenviarAlBackend(`/notificaciones${consulta}`, "GET");
}
