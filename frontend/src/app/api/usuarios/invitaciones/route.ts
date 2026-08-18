/** BFF — invite somebody into the company (HU-E1-04). */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<NextResponse> {
  return reenviarAlBackend("/usuarios/invitaciones", "POST", await cuerpoDe(request));
}
