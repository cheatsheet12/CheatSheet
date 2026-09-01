/**
 * BFF — deactivate or reactivate a service (RN-04).
 *
 * No `DELETE` handler, deliberately: the backend grants none, and deactivating is what
 * the catalogue has instead.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly servicioId: string };
}

export async function PUT(request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(
    `/servicios/${params.servicioId}/estado`,
    "PUT",
    await cuerpoDe(request),
  );
}
