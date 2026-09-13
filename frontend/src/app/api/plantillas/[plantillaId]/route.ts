/**
 * BFF — editar el cuerpo de una plantilla (HU-E11-02).
 *
 * Un 422 acá trae «La variable indicada no es válida para esta plantilla.», que es el tercer
 * criterio de la historia. La pantalla avisa antes, pero la validación que cuenta es ésta:
 * dos pestañas pasan cualquier comprobación del navegador.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly plantillaId: string };
}

export async function PUT(request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/plantillas/${params.plantillaId}`, "PUT", await cuerpoDe(request));
}
