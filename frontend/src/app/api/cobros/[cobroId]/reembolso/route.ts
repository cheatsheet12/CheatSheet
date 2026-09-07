/**
 * BFF — reembolsar un cobro (HU-E6-05).
 *
 * **Sólo el Administrador**, y el guarda vive en el caso de uso (RN-05). Un 422 acá puede
 * traer «MercadoPago rechazó el reembolso. El cobro sigue figurando como pagado.», que es lo
 * que la pantalla muestra.
 *
 * El monto viaja como **texto**: un número JSON llega como float, que es el tipo que este
 * sistema no deja acercarse a la plata.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly cobroId: string };
}

export async function POST(request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/cobros/${params.cobroId}/reembolso`, "POST", await cuerpoDe(request));
}
