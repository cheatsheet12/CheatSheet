/**
 * BFF — corregir un reembolso manual (HU-E6-05 RN-08).
 *
 * **Sólo el Administrador.** La corrección es una fila **nueva** y negativa que anula la fila
 * entera: el reembolso original no se edita ni se borra, y el motivo es obligatorio.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly cobroId: string; readonly reembolsoId: string };
}

export async function POST(request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(
    `/cobros/${params.cobroId}/reembolsos/${params.reembolsoId}/correccion`,
    "POST",
    await cuerpoDe(request),
  );
}
