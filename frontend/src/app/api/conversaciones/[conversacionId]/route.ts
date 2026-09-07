/**
 * BFF — el hilo abierto (PAN-WA-01).
 *
 * Trae el historial completo, que es la promesa de HU-E8-05 RN-03: el cliente no tiene que
 * repetir nada cuando lo atiende una persona.
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly conversacionId: string };
}

export async function GET(_request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/conversaciones/${params.conversacionId}`, "GET");
}
