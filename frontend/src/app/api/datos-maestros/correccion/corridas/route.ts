/** BFF — the runs of the correction, newest first (PAN-DM-01). */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(): Promise<NextResponse> {
  return reenviarAlBackend("/datos-maestros/correccion/corridas", "GET");
}
