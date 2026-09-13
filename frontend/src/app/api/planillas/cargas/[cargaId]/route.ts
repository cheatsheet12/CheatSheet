/** BFF — el detalle de un procesamiento y sus filas con error (HU-E3-05). */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: { params: { cargaId: string } },
): Promise<NextResponse> {
  return reenviarAlBackend(`/planillas/cargas/${params.cargaId}`, "GET");
}
