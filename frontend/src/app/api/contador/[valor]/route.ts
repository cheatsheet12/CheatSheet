/**
 * BFF — el acceso del contador externo (HU-E10-06). **La única ruta sin sesión del panel.**
 *
 * No llama a `haySesion()`, y es deliberado: el contador no tiene cuenta. Su credencial es el
 * valor del enlace, que viaja en la URL y que el backend valida contra el hash guardado —
 * junto con `revocado` y `vencimiento`, que es lo que hace que revocar corte de inmediato.
 *
 * `llamarApi` sin cookie no manda `Authorization`, así que el pedido llega igual que desde un
 * navegador cualquiera. Nada de este archivo eleva privilegios: reenvía un valor opaco.
 */

import { NextResponse } from "next/server";

import { ErrorDeApi, llamarApi } from "@/lib/api";

import { respuestaDeError } from "@/app/api/auth/_sesion";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly valor: string };
}

export async function GET(_request: Request, { params }: Contexto): Promise<NextResponse> {
  try {
    const datos = await llamarApi<unknown>(`/contador/${encodeURIComponent(params.valor)}`);
    return NextResponse.json(datos ?? {});
  } catch (error) {
    // En un 422 esto lleva «El acceso a este paquete ya no está disponible.», que es lo único
    // que el contador tiene que leer cuando el enlace deja de servir.
    return respuestaDeError(error instanceof ErrorDeApi ? error : null);
  }
}
