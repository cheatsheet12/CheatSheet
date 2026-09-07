/**
 * BFF — the company's points of sale (PAN-FAC-05).
 *
 * There is deliberately no `DELETE` handler: the backend grants none on
 * `punto_de_venta`, and a route that can only fail is worse than a route that does not
 * exist. Taking a point out of circulation is `PUT /{id}/estado`.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(): Promise<NextResponse> {
  return reenviarAlBackend("/puntos-de-venta", "GET");
}

export async function POST(request: Request): Promise<NextResponse> {
  return reenviarAlBackend("/puntos-de-venta", "POST", await cuerpoDe(request));
}
