/**
 * BFF — los paquetes contables (PAN-REP-02, HU-E10-04).
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(): Promise<NextResponse> {
  return reenviarAlBackend("/reporteria/paquetes", "GET");
}

export async function POST(request: Request): Promise<NextResponse> {
  return reenviarAlBackend("/reporteria/paquetes", "POST", await cuerpoDe(request));
}
