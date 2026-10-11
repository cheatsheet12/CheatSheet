/**
 * BFF — importar una fila corregida.
 *
 * Un rechazo de `master_data` (un CUIT que sigue mal) llega como 422 con su motivo, y el panel
 * lo muestra en el mismo editor: es lo que `reenviarAlBackend` ya hace con un 422.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  { params }: { params: { cargaId: string; numeroFila: string } },
): Promise<NextResponse> {
  return reenviarAlBackend(
    `/planillas/cargas/${params.cargaId}/filas/${params.numeroFila}/correccion`,
    "POST",
    await cuerpoDe(request),
  );
}
