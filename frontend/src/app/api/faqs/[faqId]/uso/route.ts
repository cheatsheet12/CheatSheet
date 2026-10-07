/**
 * BFF — el detalle de uso de una respuesta frecuente (HU-E9-04, ADR-0012).
 *
 * Solo lectura: todos los roles lo ven, igual que el listado.
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly faqId: string };
}

export async function GET(_request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/faqs/${params.faqId}/uso`, "GET");
}
