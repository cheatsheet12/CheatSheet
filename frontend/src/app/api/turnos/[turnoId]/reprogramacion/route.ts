/**
 * BFF — reprogramar un turno (HU-E7-02 RN-01, RN-02).
 *
 * **Conserva el estado.** No hay un campo `estado` en el cuerpo y no lo va a haber: la historia
 * dice con todas las letras que reprogramar no es un estado.
 *
 * Un 422 acá trae «El horario seleccionado no está disponible.» y el turno **queda donde
 * estaba** — lo garantiza el rollback de la transacción, no esta ruta.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly turnoId: string };
}

export async function POST(request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(
    `/turnos/${params.turnoId}/reprogramacion`,
    "POST",
    await cuerpoDe(request),
  );
}
