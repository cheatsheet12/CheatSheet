/** BFF — corregir la asignación de una columna (HU-E3-02 RN-01). */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function PUT(
  request: Request,
  { params }: { params: { mapeoId: string } },
): Promise<NextResponse> {
  return reenviarAlBackend(
    `/planillas/mapeos/${params.mapeoId}/columnas`,
    "PUT",
    await cuerpoDe(request),
  );
}
