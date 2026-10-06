/**
 * BFF — volver a revisar un mapeo confirmado (HU-E3-02 RN-01).
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function POST(
  _request: Request,
  { params }: { params: { mapeoId: string } },
): Promise<NextResponse> {
  return reenviarAlBackend(`/planillas/mapeos/${params.mapeoId}/revision`, "POST");
}
