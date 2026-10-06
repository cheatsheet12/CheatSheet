/**
 * BFF — the company's linked spreadsheets (PAN-ING-01, `Cargas recientes`).
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(): Promise<NextResponse> {
  return reenviarAlBackend("/planillas", "GET");
}
