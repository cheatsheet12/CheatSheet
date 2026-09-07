/**
 * BFF — qué servicios se prestan en un recurso (HU-E7-04 RN-02).
 *
 * `PUT` por lo mismo que la disponibilidad: reemplaza la lista entera.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly recursoId: string };
}

export async function PUT(request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(
    `/recursos/${params.recursoId}/servicios`,
    "PUT",
    await cuerpoDe(request),
  );
}
