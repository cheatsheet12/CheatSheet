/**
 * BFF — el detalle de un cobro (PAN-COB-02).
 *
 * `GET` solamente. Las tres acciones que cambian el estado tienen su propia ruta, porque cada
 * una lleva un cuerpo distinto y porque son las que Solo Lectura no puede tocar.
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly cobroId: string };
}

export async function GET(_request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/cobros/${params.cobroId}`, "GET");
}
