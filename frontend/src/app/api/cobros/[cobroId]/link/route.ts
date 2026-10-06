/**
 * BFF — regenerar el link de pago (HU-E6-03, último criterio).
 *
 * El backend invalida el anterior y activa el nuevo, y registra el cambio en la bitácora.
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly cobroId: string };
}

export async function POST(_request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/cobros/${params.cobroId}/link`, "POST", {});
}
