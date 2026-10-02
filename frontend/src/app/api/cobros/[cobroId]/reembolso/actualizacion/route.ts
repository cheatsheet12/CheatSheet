/**
 * BFF — «Actualizar estado» de un reembolso en proceso (HU-E6-05).
 *
 * **Sólo el Administrador**, y el guarda vive en el caso de uso. No lleva cuerpo: el cobro ya
 * tiene guardado el monto y la clave de idempotencia de lo que se pidió.
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

interface Contexto {
  readonly params: { readonly cobroId: string };
}

export async function POST(_request: Request, { params }: Contexto): Promise<NextResponse> {
  return reenviarAlBackend(`/cobros/${params.cobroId}/reembolso/actualizacion`, "POST", {});
}
