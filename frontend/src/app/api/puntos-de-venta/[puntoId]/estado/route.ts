/**
 * BFF — activate or deactivate a point of sale (HU-E5-05 RN-04).
 *
 * This is what `billing` has instead of a delete. Reactivating re-checks ARCA on the
 * backend, so a 422 here can carry «El punto de venta no está habilitado en ARCA.» for a
 * point that was registered without trouble months ago.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly puntoId: string };
}

export async function PUT(request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(
    `/puntos-de-venta/${params.puntoId}/estado`,
    "PUT",
    await cuerpoDe(request),
  );
}
