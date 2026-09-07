/**
 * BFF — el horario semanal de un recurso (HU-E7-04 RN-01).
 *
 * `PUT` y no `POST` porque **reemplaza**: un recurso tiene un horario de atención, no un
 * catálogo de horarios. Guardarlo por partes obligaría a decidir qué pasa cuando una franja
 * nueva pisa a otra vieja.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly recursoId: string };
}

export async function PUT(request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(
    `/recursos/${params.recursoId}/disponibilidad`,
    "PUT",
    await cuerpoDe(request),
  );
}
