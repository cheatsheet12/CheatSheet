/** BFF — read and toggle a service's categories (HU-E4-04). */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly servicioId: string };
}

export async function GET(_request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/servicios/${params.servicioId}/categorias`, "GET");
}

export async function PUT(request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(
    `/servicios/${params.servicioId}/categorias`,
    "PUT",
    await cuerpoDe(request),
  );
}
