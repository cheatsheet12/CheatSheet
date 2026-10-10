/**
 * BFF — accepting the legal documents in force (HU-E1-03 RN-03, HU-E1-08 RN-05).
 *
 * The backend validates everything that matters (the version must be the one in force, the
 * terms need an Administrador); this forwards the body untouched. Needs a session, and the
 * backend lets this route through even while a document is pending: it is how the block ends.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<NextResponse> {
  return reenviarAlBackend("/legal/aceptaciones", "POST", await cuerpoDe(request));
}
