/**
 * BFF — la descarga del paquete por el enlace del contador (HU-E10-06). **Sin sesión.**
 *
 * El backend revalida el enlace en cada descarga, no sólo al entrar: una pestaña abierta no
 * sigue bajando documentación fiscal después de que el administrador apretó «revocar».
 */

import { ErrorDeApi, descargarBinario } from "@/lib/api";

import { respuestaDeError } from "@/app/api/auth/_sesion";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly valor: string; readonly paqueteId: string };
}

export async function GET(_request: Request, { params }: Contexto): Promise<Response> {
  try {
    const archivo = await descargarBinario(
      `/contador/${encodeURIComponent(params.valor)}/paquetes/${params.paqueteId}`,
    );
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
