/**
 * BFF — la previsualización de un reporte (HU-E10-02).
 *
 * `GET` y no `POST`, y no es una preferencia de estilo: **esta ruta no crea nada** (RN-03).
 * Un verbo que sugiera lo contrario haría que alguien la ponga detrás de una confirmación.
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<NextResponse> {
  const consulta = new URL(request.url).search;
  return reenviarAlBackend(`/reporteria/previsualizacion${consulta}`, "GET");
}
