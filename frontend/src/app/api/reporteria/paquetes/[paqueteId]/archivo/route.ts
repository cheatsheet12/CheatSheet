/**
 * BFF — el ZIP de un paquete contable (HU-E10-04).
 *
 * Mismo camino que el archivo de un reporte, y por lo mismo: son bytes, no JSON.
 */

import { NextResponse } from "next/server";

import { ErrorDeApi, descargarBinario } from "@/lib/api";
import { haySesion } from "@/lib/session";

import { respuestaDeError } from "@/app/api/auth/_sesion";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly paqueteId: string };
}

export async function GET(_request: Request, { params }: Contexto): Promise<Response> {
  if (!haySesion()) {
    return NextResponse.json({ error: "NoAutenticado" }, { status: 401 });
  }
  try {
    const archivo = await descargarBinario(`/reporteria/paquetes/${params.paqueteId}/archivo`);
    return new Response(archivo.contenido, {
      status: 200,
      headers: {
        "Content-Type": archivo.tipo,
        "Content-Disposition": archivo.disposicion,
      },
    });
  } catch (error) {
    return respuestaDeError(error instanceof ErrorDeApi ? error : null);
  }
}
