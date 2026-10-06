/**
 * BFF — registrar una excepción de disponibilidad (HU-E7-05).
 *
 * Un feriado, unas vacaciones o una apertura fuera de horario. Una sola por fecha: la segunda
 * contesta 422 con «Ya existe una excepción para esa fecha en este recurso.», y quien lo
 * garantiza es un índice único, no una comprobación.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly recursoId: string };
}

export async function POST(request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(
    `/recursos/${params.recursoId}/excepciones`,
    "POST",
    await cuerpoDe(request),
  );
}
