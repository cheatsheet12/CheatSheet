/**
 * BFF — the Google callback's landing point (HU-E2-04 RN-01).
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<NextResponse> {
  return reenviarAlBackend("/planillas/google", "POST", await cuerpoDe(request));
}
