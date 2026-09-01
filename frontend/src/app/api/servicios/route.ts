/**
 * BFF — the company's service catalogue (PAN-DM-02).
 *
 * The query string is forwarded verbatim, for the reason the clients route states: this
 * file does not learn the filter names, so a new filter is one change and not two.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<NextResponse> {
  const consulta = new URL(request.url).search;
  return reenviarAlBackend(`/servicios${consulta}`, "GET");
}

export async function POST(request: Request): Promise<NextResponse> {
  return reenviarAlBackend("/servicios", "POST", await cuerpoDe(request));
}
