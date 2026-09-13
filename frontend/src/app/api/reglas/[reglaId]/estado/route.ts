/**
 * BFF — activar o desactivar una regla (HU-E11-01 RN-04).
 *
 * Esto es lo que la configuración tiene en lugar de un borrado. Desactivar deja de aplicar de
 * inmediato y no toca nada de lo ya procesado.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly reglaId: string };
}

export async function PUT(request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/reglas/${params.reglaId}/estado`, "PUT", await cuerpoDe(request));
}
