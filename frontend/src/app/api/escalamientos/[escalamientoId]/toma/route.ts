/**
 * BFF — tomar un escalamiento (HU-E9-01 RN-02, RN-06).
 *
 * Sin cuerpo: quién lo toma sale de la sesión, no de lo que mande el navegador. Queda
 * registrado con el operador y el timestamp.
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly escalamientoId: string };
}

export async function POST(_request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/escalamientos/${params.escalamientoId}/toma`, "POST", {});
}
