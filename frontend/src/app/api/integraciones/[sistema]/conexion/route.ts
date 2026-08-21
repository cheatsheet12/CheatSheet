/**
 * BFF — connecting one integration. Administrador only, enforced by the backend.
 *
 * `PUT` because connecting twice is the same result once: the credential is replaced, not
 * accumulated.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe } from "@/app/api/usuarios/_proxy";
import { reenviarIntegracion } from "@/app/api/integraciones/_proxy";

export const dynamic = "force-dynamic";

export async function PUT(
  request: Request,
  { params }: { params: { sistema: string } },
): Promise<NextResponse> {
  return reenviarIntegracion(
    `/integraciones/${encodeURIComponent(params.sistema)}/conexion`,
    "PUT",
    await cuerpoDe(request),
  );
}
