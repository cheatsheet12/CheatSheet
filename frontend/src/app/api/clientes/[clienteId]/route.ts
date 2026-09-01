/** BFF — edit one client (HU-E4-01). */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly clienteId: string };
}

export async function PUT(request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/clientes/${params.clienteId}`, "PUT", await cuerpoDe(request));
}
