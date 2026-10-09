/**
 * BFF — enviar una plantilla a revisión de Meta (U6, PAN-CFG-NOT).
 *
 * Sin cuerpo: qué plantilla es sale de la ruta y quién la reenvía, de la sesión. Un 422 trae el
 * texto de Meta (la plantilla no se aceptó y no cambió nada); un 503, que Meta no respondió.
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly plantillaId: string };
}

export async function POST(_request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/plantillas/${params.plantillaId}/envio`, "POST", {});
}
