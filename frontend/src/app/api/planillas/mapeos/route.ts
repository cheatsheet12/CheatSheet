/** BFF — proponer el mapeo de una planilla (HU-E3-01, PAN-ING-02). */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<NextResponse> {
  return reenviarAlBackend("/planillas/mapeos", "POST", await cuerpoDe(request));
}
