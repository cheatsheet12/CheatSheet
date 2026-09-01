/**
 * BFF — read and toggle a client's categories (HU-E4-04).
 *
 * `GET` is what the checkboxes open with; `PUT` toggles one, assigning or removing
 * according to `asignar`, and answers with the element's new set.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly clienteId: string };
}

export async function GET(_request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/clientes/${params.clienteId}/categorias`, "GET");
}

export async function PUT(request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(
    `/clientes/${params.clienteId}/categorias`,
    "PUT",
    await cuerpoDe(request),
  );
}
