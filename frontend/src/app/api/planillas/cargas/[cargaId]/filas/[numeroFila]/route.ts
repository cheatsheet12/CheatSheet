/** BFF — los valores de una fila que falló, para editarla en pantalla. */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: { params: { cargaId: string; numeroFila: string } },
): Promise<NextResponse> {
  return reenviarAlBackend(`/planillas/cargas/${params.cargaId}/filas/${params.numeroFila}`, "GET");
}
