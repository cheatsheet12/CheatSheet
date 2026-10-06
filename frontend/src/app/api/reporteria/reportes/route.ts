/**
 * BFF — los reportes de la empresa (PAN-REP-01, HU-E10-03).
 *
 * **No hay `DELETE`.** El historial es lo que contesta «qué le mandé a mi contador y cuándo»;
 * el backend no otorga el permiso, así que una función acá sólo podría fallar.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(): Promise<NextResponse> {
  return reenviarAlBackend("/reporteria/reportes", "GET");
}

export async function POST(request: Request): Promise<NextResponse> {
  const consulta = new URL(request.url).search;
  return reenviarAlBackend(`/reporteria/reportes${consulta}`, "POST", await cuerpoDe(request));
}
