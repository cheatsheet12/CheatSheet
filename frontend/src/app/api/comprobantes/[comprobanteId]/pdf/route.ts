/**
 * BFF — the printable representation of a document (HU-E5-02 RN-03).
 *
 * **The one route in this BFF that does not go through `reenviarAlBackend`**, and it has
 * to be: that helper parses the response as JSON, and this answers bytes. It uses
 * `descargarBinario` instead, which shares the bearer token, the timeout and the error
 * translation with every other call — the three things a route rolling its own `fetch`
 * would get subtly wrong.
 *
 * The session check is still the first thing: a document's PDF carries a customer's CUIT,
 * address and amounts, and no cookie means no bytes.
 */

import { NextResponse } from "next/server";

import { ErrorDeApi, descargarBinario } from "@/lib/api";
import { haySesion } from "@/lib/session";

import { respuestaDeError } from "@/app/api/auth/_sesion";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly comprobanteId: string };
}

export async function GET(_request: Request, { params }: Contexto): Promise<Response> {
  if (!haySesion()) {
    return NextResponse.json({ error: "NoAutenticado" }, { status: 401 });
  }

  try {
    const archivo = await descargarBinario(`/comprobantes/${params.comprobanteId}/pdf`);
    return new Response(archivo.contenido, {
      status: 200,
      headers: {
        "Content-Type": archivo.tipo,
        // Forwarded as the backend set it: `inline`, with the fiscal number as the
        // filename, so the browser shows it and whoever wants the file saves it.
        "Content-Disposition": archivo.disposicion,
      },
    });
  } catch (error) {
    // On a 422 this carries «este comprobante todavia no fue autorizado...», which is what
    // the screen shows instead of an empty tab.
    return respuestaDeError(error instanceof ErrorDeApi ? error : null);
  }
}
