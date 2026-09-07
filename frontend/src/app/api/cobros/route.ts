/**
 * BFF — los cobros de la empresa (PAN-COB-01, PAN-COB-03).
 *
 * El query string se reenvía entero, por lo que dice la ruta de clientes: este archivo no
 * aprende los nombres de los filtros, así que un filtro nuevo es un cambio y no dos.
 *
 * **No hay `DELETE`.** Un cobro pagado es plata que entró: se reembolsa. Uno pendiente se
 * cancela, que deja el motivo. El backend no otorga el permiso.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<NextResponse> {
  const consulta = new URL(request.url).search;
  return reenviarAlBackend(`/cobros${consulta}`, "GET");
}

export async function POST(request: Request): Promise<NextResponse> {
  return reenviarAlBackend("/cobros", "POST", await cuerpoDe(request));
}
