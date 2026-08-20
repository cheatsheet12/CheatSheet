/**
 * BFF — starting an OAuth2 authorization. Administrador only, enforced by the backend.
 *
 * `POST` and not `GET`: it mints a `state` and stores it, so it is not something a
 * prefetch or a reload may repeat for free.
 */

import type { NextResponse } from "next/server";

import { reenviarIntegracion } from "@/app/api/integraciones/_proxy";

export const dynamic = "force-dynamic";

export async function POST(
  _request: Request,
  { params }: { params: { sistema: string } },
): Promise<NextResponse> {
  return reenviarIntegracion(
    `/integraciones/${encodeURIComponent(params.sistema)}/autorizacion`,
    "POST",
  );
}
