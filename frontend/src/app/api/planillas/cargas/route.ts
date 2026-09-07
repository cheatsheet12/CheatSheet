/** BFF — encolar un procesamiento y listar las cargas (HU-E3-03, HU-E3-05). */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<NextResponse> {
  return reenviarAlBackend(`/planillas/cargas${new URL(request.url).search}`, "GET");
}

export async function POST(request: Request): Promise<NextResponse> {
  return reenviarAlBackend("/planillas/cargas", "POST", await cuerpoDe(request));
}
