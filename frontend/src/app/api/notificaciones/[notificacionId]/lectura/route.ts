/**
 * BFF — el acuse de lectura de una notificación (HU-E11-03 RN-03).
 *
 * `POST` sobre un sub-recurso y no `PATCH` sobre la notificación: lo que se crea es el acuse, y
 * no hay forma de deshacerlo — «lo vi» es un hecho, no una preferencia de interfaz.
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly notificacionId: string };
}

export async function POST(_request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/notificaciones/${params.notificacionId}/lectura`, "POST", {});
}
