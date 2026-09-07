/**
 * BFF — editar y eliminar una respuesta frecuente (HU-E9-04).
 *
 * **El único `DELETE` del producto que borra de verdad.** RN-03 pide que una FAQ eliminada
 * deje de estar disponible «de forma inmediata», y una FAQ no es un registro del negocio: no
 * hay nada que auditar en una pregunta que ya no se hace. Todo lo demás se desactiva.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly faqId: string };
}

export async function PUT(request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/faqs/${params.faqId}`, "PUT", await cuerpoDe(request));
}

export async function DELETE(_request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/faqs/${params.faqId}`, "DELETE");
}
