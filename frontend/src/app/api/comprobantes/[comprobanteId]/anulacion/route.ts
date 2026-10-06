/**
 * BFF — how much of a document has been reversed (HU-E5-04 RN-05).
 *
 * Derived on every read from the authorised credit notes (decision D19), never from a
 * column: the answer this returns is recomputed, so it cannot be stale.
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly comprobanteId: string };
}

export async function GET(_request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/comprobantes/${params.comprobanteId}/anulacion`, "GET");
}
