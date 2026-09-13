/** BFF — confirmar el mapeo, que es lo que habilita procesar la planilla (RN-03). */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  { params }: { params: { mapeoId: string } },
): Promise<NextResponse> {
  return reenviarAlBackend(
    `/planillas/mapeos/${params.mapeoId}/confirmacion`,
    "POST",
    await cuerpoDe(request),
  );
}
