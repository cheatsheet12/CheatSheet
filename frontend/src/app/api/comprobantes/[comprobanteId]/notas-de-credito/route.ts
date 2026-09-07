/**
 * BFF — emitting a credit note against one document (HU-E5-04).
 *
 * `POST` only, and the body carries **only the lines being reversed**: the type and the
 * receptor come from the original (RN-02), and accepting them here would let a caller
 * choose which kind of document reverses which — which ARCA rejects.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly comprobanteId: string };
}

export async function POST(request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(
    `/comprobantes/${params.comprobanteId}/notas-de-credito`,
    "POST",
    await cuerpoDe(request),
  );
}
