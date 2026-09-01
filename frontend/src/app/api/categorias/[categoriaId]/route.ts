/**
 * BFF — edit or delete one category (HU-E4-03).
 *
 * **The only `DELETE` in this app**, and the reason is in migration 0010: a category is
 * referenced by nothing outside `master_data`, and RN-03 says the classified elements
 * lose the label and keep everything else. `/clientes` and `/servicios` have none.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly categoriaId: string };
}

export async function PUT(request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/categorias/${params.categoriaId}`, "PUT", await cuerpoDe(request));
}

export async function DELETE(_request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/categorias/${params.categoriaId}`, "DELETE");
}
