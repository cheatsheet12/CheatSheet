/**
 * BFF — el detalle de una operación (PAN-LOG-02, HU-E12-02).
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly operacionId: string };
}

export async function GET(_request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/bitacora/${params.operacionId}`, "GET");
}
