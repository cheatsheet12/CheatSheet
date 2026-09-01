/**
 * BFF — the company's customer catalogue (PAN-DM-01).
 *
 * Readable by any role that reaches the screen: the navigation map §5 grades Datos
 * Maestros read-only for Solo Lectura, and what each role may *do* is decided by the
 * backend, not here.
 *
 * The query string is forwarded verbatim rather than rebuilt field by field. Rebuilding
 * it would mean this file learning the filter names, and gaining a new one — the category
 * filter of `categorias-y-clasificacion` — would then mean editing two places.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<NextResponse> {
  const consulta = new URL(request.url).search;
  return reenviarAlBackend(`/clientes${consulta}`, "GET");
}

export async function POST(request: Request): Promise<NextResponse> {
  return reenviarAlBackend("/clientes", "POST", await cuerpoDe(request));
}
