/**
 * BFF — el archivo de un reporte (HU-E10-03).
 *
 * No pasa por `reenviarAlBackend`: ese helper parsea la respuesta como JSON y esto contesta
 * bytes. Usa `descargarBinario`, que comparte el token, el timeout y la traducción de errores
 * con el resto de las llamadas — las tres cosas que una ruta con su propio `fetch` haría mal
 * sin que se note.
 *
 * La sesión se comprueba primero: un CSV de facturación es la lista de clientes de la empresa
 * con sus CUIT.
 */

import { NextResponse } from "next/server";

import { ErrorDeApi, descargarBinario } from "@/lib/api";
import { haySesion } from "@/lib/session";

import { respuestaDeError } from "@/app/api/auth/_sesion";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly reporteId: string };
}

export async function GET(_request: Request, { params }: Contexto): Promise<Response> {
  if (!haySesion()) {
    return NextResponse.json({ error: "NoAutenticado" }, { status: 401 });
  }
  try {
    const archivo = await descargarBinario(`/reporteria/reportes/${params.reporteId}/archivo`);
    return new Response(archivo.contenido, {
      status: 200,
      headers: {
        "Content-Type": archivo.tipo,
        // Reenviado tal como lo armó el backend: `attachment`, con el nombre que dice el tipo
        // y el período. Esto se guarda, no se mira en una pestaña.
        "Content-Disposition": archivo.disposicion,
      },
    });
  } catch (error) {
    return respuestaDeError(error instanceof ErrorDeApi ? error : null);
  }
}
