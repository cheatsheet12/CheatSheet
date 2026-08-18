/** BFF — change somebody's role (HU-E1-05). */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly usuarioId: string };
}

export async function PATCH(request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/usuarios/${params.usuarioId}/rol`, "PATCH", await cuerpoDe(request));
}
