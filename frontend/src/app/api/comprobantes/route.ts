/**
 * BFF — the company's issued documents (PAN-FAC-01, PAN-FAC-03).
 *
 * The query string is forwarded verbatim, for the reason the clients route states: this
 * file does not learn the filter names, so a new filter is one change and not two.
 *
 * **There is no `DELETE` and no `PUT`.** A document with a CAE is a legal record; it is
 * reversed with a credit note, which is a different document. The backend grants neither,
 * so a route here could only ever fail.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<NextResponse> {
  const consulta = new URL(request.url).search;
  return reenviarAlBackend(`/comprobantes${consulta}`, "GET");
}

export async function POST(request: Request): Promise<NextResponse> {
  return reenviarAlBackend("/comprobantes", "POST", await cuerpoDe(request));
}
