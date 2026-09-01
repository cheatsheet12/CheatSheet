/** BFF — the company's own labels (PAN-DM-03). */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<NextResponse> {
  const consulta = new URL(request.url).search;
  return reenviarAlBackend(`/categorias${consulta}`, "GET");
}

export async function POST(request: Request): Promise<NextResponse> {
  return reenviarAlBackend("/categorias", "POST", await cuerpoDe(request));
}
