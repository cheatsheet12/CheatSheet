/**
 * BFF — cancelar un turno (HU-E7-02).
 *
 * **Sin cuerpo**, a diferencia de cancelar un cobro. La diferencia es del negocio: allá se da
 * de baja una deuda y la historia pide el motivo (HU-E6-04 RN-02); acá se libera una franja y
 * ninguna historia lo pide.
 *
 * El backend avisa al cliente por WhatsApp si tiene número registrado (RN-03), y el aviso no
 * puede voltear la cancelación.
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly turnoId: string };
}

export async function POST(_request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/turnos/${params.turnoId}/cancelacion`, "POST", {});
}
