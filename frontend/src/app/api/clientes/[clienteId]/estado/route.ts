/**
 * BFF — deactivate or reactivate a client.
 *
 * This is what the catalogue has instead of a delete, so there is deliberately no
 * `DELETE` handler here either: the backend grants none, and a route that can only fail
 * is worse than a route that does not exist.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly clienteId: string };
}

export async function PUT(request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/clientes/${params.clienteId}/estado`, "PUT", await cuerpoDe(request));
}
