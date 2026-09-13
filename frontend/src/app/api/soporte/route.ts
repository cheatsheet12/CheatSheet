/**
 * BFF — las solicitudes de soporte (PAN-SOP-01, HU-E9-03).
 *
 * **Sin `DELETE` y sin `PUT`.** El estado lo mueve el equipo de CheatSheet (RN-03), y un
 * pedido de ayuda borrado es un pedido que nadie puede demostrar que hizo.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<NextResponse> {
  const consulta = new URL(request.url).search;
  return reenviarAlBackend(`/soporte${consulta}`, "GET");
}

export async function POST(request: Request): Promise<NextResponse> {
  return reenviarAlBackend("/soporte", "POST", await cuerpoDe(request));
}
