/**
 * BFF — validating the receptor's CUIT against ARCA's registry (HU-E5-03 RN-02).
 *
 * The first step of PAN-FAC-03 and the one that gates the rest of the form. A 422 here
 * carries the story's own sentence — «El CUIT ingresado no es válido…» or «No se encontró
 * el CUIT en el padrón de ARCA.» — which is exactly what the screen shows.
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly cuit: string };
}

export async function GET(_request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/comprobantes/receptores/${encodeURIComponent(params.cuit)}`, "GET");
}
