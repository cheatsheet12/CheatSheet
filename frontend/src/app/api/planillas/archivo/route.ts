/**
 * BFF — the drop zone of PAN-ING-01 (HU-E3-03).
 *
 * The only route in this app that forwards a binary body. It reads the whole request into
 * memory, which is bounded: the backend refuses anything over 25 MB and so does the
 * browser side before it ever posts.
 *
 * The file name travels in the query string rather than a header because Spanish file
 * names carry accents, and `clientes año 2026.xlsx` in a header needs encoding rules that
 * a query parameter already has.
 */

import { NextResponse } from "next/server";

import { ErrorDeApi, subirBinario } from "@/lib/api";
import { haySesion } from "@/lib/session";

import { respuestaDeError } from "@/app/api/auth/_sesion";

export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<NextResponse> {
  if (!haySesion()) {
    return NextResponse.json({ error: "NoAutenticado" }, { status: 401 });
  }

  const nombre = new URL(request.url).searchParams.get("nombre");
  if (nombre === null || nombre.trim() === "") {
    return NextResponse.json({ error: "EntradaInvalida", detalle: "Falta el nombre del archivo" }, { status: 422 });
  }

  try {
    const contenido = await request.arrayBuffer();
    const datos = await subirBinario<unknown>(
      `/planillas/archivo?nombre=${encodeURIComponent(nombre)}`,
      contenido,
    );
    return NextResponse.json(datos ?? {}, { status: 201 });
  } catch (error) {
    return respuestaDeError(error instanceof ErrorDeApi ? error : null);
  }
}
