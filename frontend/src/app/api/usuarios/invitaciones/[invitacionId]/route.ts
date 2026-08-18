/** BFF — revoke a pending invitation (HU-E1-04 RN-04). */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly invitacionId: string };
}

export async function DELETE(_request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/usuarios/invitaciones/${params.invitacionId}`, "DELETE");
}
