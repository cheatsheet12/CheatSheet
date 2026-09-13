/**
 * BFF — el operador le escribe al cliente (HU-E9-01, tercer criterio).
 *
 * **Requiere el escalamiento tomado.** Un 422 acá significa que el agente todavía está
 * contestando ese hilo, y mandar un mensaje encima le daría al cliente dos interlocutores.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly conversacionId: string };
}

export async function POST(request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(
    `/conversaciones/${params.conversacionId}/mensajes`,
    "POST",
    await cuerpoDe(request),
  );
}
