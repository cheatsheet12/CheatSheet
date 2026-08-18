/** BFF — deactivate a user (HU-E1-06). */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly usuarioId: string };
}

export async function POST(_request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/usuarios/${params.usuarioId}/desactivacion`, "POST", {});
}
