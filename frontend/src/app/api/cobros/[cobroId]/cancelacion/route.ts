/**
 * BFF — cancelar un cobro (HU-E6-04).
 *
 * El motivo viaja en el cuerpo y lo valida el backend: dos pestañas pasan la validación del
 * navegador, y RN-04 pide que el motivo quede en la bitácora.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly cobroId: string };
}

export async function POST(request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(
    `/cobros/${params.cobroId}/cancelacion`,
    "POST",
    await cuerpoDe(request),
  );
}
