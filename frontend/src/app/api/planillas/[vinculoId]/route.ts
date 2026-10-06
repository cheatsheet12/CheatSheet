/**
 * BFF — unlinking a spreadsheet (PAN-ING-01).
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function DELETE(
  _request: Request,
  { params }: { params: { vinculoId: string } },
): Promise<NextResponse> {
  return reenviarAlBackend(`/planillas/${params.vinculoId}`, "DELETE");
}
