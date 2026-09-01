/**
 * BFF — the «Validar contra ARCA» button of the client form.
 *
 * A `POST` on a read, like the onboarding's equivalent: the CUIT is somebody's tax id,
 * and in a query string it would end up in access logs and in browser history.
 *
 * The static segment wins over `[clienteId]` in Next's matcher, so `/api/clientes/padron`
 * never reaches the edit route.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<NextResponse> {
  return reenviarAlBackend("/clientes/padron", "POST", await cuerpoDe(request));
}
