/**
 * BFF — quitar la excepción de una fecha (HU-E7-05).
 *
 * **El único `DELETE` del épico**, y no borra una entidad del negocio: una excepción es una
 * anotación sobre un calendario, y sacarla es volver al horario habitual. Corregir una es
 * quitarla y volver a agregarla, lo que evita tener que decidir qué significa cambiarle el
 * tipo.
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly recursoId: string; readonly fecha: string };
}

export async function DELETE(_request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/recursos/${params.recursoId}/excepciones/${params.fecha}`, "DELETE");
}
