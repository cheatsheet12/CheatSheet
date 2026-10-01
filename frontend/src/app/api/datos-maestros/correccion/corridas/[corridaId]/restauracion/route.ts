/** BFF — restore one run of the correction (PAN-DM-01). */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly corridaId: string };
}

export async function POST(_request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/datos-maestros/correccion/${params.corridaId}/restauracion`, "POST");
}
