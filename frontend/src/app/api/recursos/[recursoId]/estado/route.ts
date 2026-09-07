/**
 * BFF — activar o desactivar un recurso (HU-E7-04 RN-03).
 *
 * Esto es lo que la configuración tiene en lugar de un borrado. Desactivar impide reservas
 * nuevas **y no toca los turnos ya reservados**, que es lo que la regla dice.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly recursoId: string };
}

export async function PUT(request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/recursos/${params.recursoId}/estado`, "PUT", await cuerpoDe(request));
}
