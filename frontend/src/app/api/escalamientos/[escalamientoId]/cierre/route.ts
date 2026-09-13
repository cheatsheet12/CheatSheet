/**
 * BFF — cerrar un escalamiento (HU-E9-02).
 *
 * Un 422 acá puede traer «Un escalamiento cerrado no se reabre. Un nuevo pedido del cliente
 * genera uno nuevo.», que es el tercer criterio de la historia — y por eso el detalle importa:
 * este BFF reenvía el texto sólo en un 422, y la historia pide **decirlo**, no sólo negarlo.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly escalamientoId: string };
}

export async function POST(request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(
    `/escalamientos/${params.escalamientoId}/cierre`,
    "POST",
    await cuerpoDe(request),
  );
}
