/**
 * BFF — los horarios que un recurso ofrece un día (HU-E7-06).
 *
 * **La respuesta puede quedar vieja en un segundo.** Marca lo que estaba tomado al momento de
 * la consulta; quien decide si una franja está libre es la restricción de exclusión de
 * PostgreSQL (decisión D28), y reservar puede fallar igual.
 *
 * Ruta propia y no un parámetro de `/turnos` porque contesta otra pregunta: no «qué turnos
 * hay» sino «qué horarios existen», que incluye los que están vacíos.
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<NextResponse> {
  const consulta = new URL(request.url).search;
  return reenviarAlBackend(`/turnos/disponibilidad${consulta}`, "GET");
}
