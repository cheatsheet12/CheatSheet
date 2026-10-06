/**
 * BFF — la bandeja de conversaciones (PAN-WA-01).
 *
 * **No hay `DELETE`.** Una conversación es el registro de lo que se le dijo a un cliente. El
 * backend no otorga el permiso, así que una ruta acá sólo podría fallar.
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<NextResponse> {
  const consulta = new URL(request.url).search;
  return reenviarAlBackend(`/conversaciones${consulta}`, "GET");
}
