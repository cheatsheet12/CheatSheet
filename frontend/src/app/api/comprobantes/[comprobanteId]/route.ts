/**
 * BFF — one document's detail (PAN-FAC-02).
 *
 * `GET` only. RN-01 makes an authorised document immutable, so there is deliberately no
 * `PUT` here either — the backend refuses it and a route that can only fail is worse than
 * one that does not exist.
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly comprobanteId: string };
}

export async function GET(_request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/comprobantes/${params.comprobanteId}`, "GET");
}
