/**
 * BFF — finishing an OAuth2 authorization: the code comes back and becomes a credential.
 *
 * The `code` and the `state` travel in the body rather than in the query string, so they
 * stay out of the browser history and out of any access log between here and the backend.
 */

import type { NextResponse } from "next/server";

import { reenviarIntegracion } from "@/app/api/integraciones/_proxy";
import { cuerpoDe } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  { params }: { params: { sistema: string } },
): Promise<NextResponse> {
  return reenviarIntegracion(
    `/integraciones/${encodeURIComponent(params.sistema)}/autorizacion/canje`,
    "POST",
    await cuerpoDe(request),
  );
}
