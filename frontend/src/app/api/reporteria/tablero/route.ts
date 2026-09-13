/**
 * BFF — el tablero de indicadores (PAN-REP-01, HU-E10-01).
 *
 * El query string se reenvía entero, por lo que dicen las demás rutas: este archivo no aprende
 * los nombres de los filtros, así que un filtro nuevo es un cambio y no dos.
 *
 * **Todos los roles leen** (RN-04 y RN-05): lo que viaja son totales, y un total no identifica
 * a nadie. Quien decide sigue siendo el backend; acá lo único que se exige es la sesión.
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<NextResponse> {
  const consulta = new URL(request.url).search;
  return reenviarAlBackend(`/reporteria/tablero${consulta}`, "GET");
}
