/**
 * BFF — la bitácora de operaciones (PAN-LOG-01, HU-E12-01).
 *
 * El query string se reenvía entero, por lo que dicen las demás rutas: este archivo no aprende
 * los nombres de los filtros, así que un filtro nuevo es un cambio y no dos.
 *
 * **No hay `POST`, `PUT` ni `DELETE`.** RN-04: la bitácora es de sólo consulta, y el backend no
 * otorga esos permisos ni siquiera al rol de la aplicación.
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<NextResponse> {
  const consulta = new URL(request.url).search;
  return reenviarAlBackend(`/bitacora${consulta}`, "GET");
}
