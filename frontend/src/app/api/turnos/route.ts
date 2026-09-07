/**
 * BFF — la agenda de la empresa (PAN-AGE-01, PAN-AGE-02).
 *
 * El query string se reenvía entero, por lo que dicen las demás rutas: este archivo no aprende
 * los nombres de los filtros, así que un filtro nuevo es un cambio y no dos.
 *
 * **No hay `DELETE`.** Un turno se cancela: queda en la agenda con su estado, que es lo que
 * hace auditable la ocupación de un recurso. El backend no otorga el permiso.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<NextResponse> {
  const consulta = new URL(request.url).search;
  return reenviarAlBackend(`/turnos${consulta}`, "GET");
}

export async function POST(request: Request): Promise<NextResponse> {
  return reenviarAlBackend("/turnos", "POST", await cuerpoDe(request));
}
