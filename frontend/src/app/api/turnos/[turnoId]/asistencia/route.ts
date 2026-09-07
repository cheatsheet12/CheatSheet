/**
 * BFF — marcar asistencia o inasistencia (HU-E7-03).
 *
 * Una sola ruta con un booleano en vez de dos rutas: son la misma decisión con dos valores, y
 * dos rutas obligarían a la pantalla a elegir cuál llamar en lugar de mandar lo que el usuario
 * apretó.
 *
 * Un turno futuro contesta 409 con «El turno aún no transcurrió.» (RN-01).
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly turnoId: string };
}

export async function POST(request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/turnos/${params.turnoId}/asistencia`, "POST", await cuerpoDe(request));
}
