/**
 * BFF — «Registrar reembolso» de una transferencia (HU-E6-05 RN-07).
 *
 * **Sólo el Administrador.** El monto viaja como **texto** y la fecha como día (`YYYY-MM-DD`):
 * un número JSON llega como float, que es el tipo que este sistema no deja acercarse a la plata.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly cobroId: string };
}

export async function POST(request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/cobros/${params.cobroId}/reembolsos`, "POST", await cuerpoDe(request));
}
