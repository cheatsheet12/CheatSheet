/** BFF — reprocesar sólo las filas que fallaron (HU-E3-06 RN-02). */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function POST(
  _request: Request,
  { params }: { params: { cargaId: string } },
): Promise<NextResponse> {
  return reenviarAlBackend(`/planillas/cargas/${params.cargaId}/reproceso`, "POST");
}
