/**
 * BFF — los encabezados de una planilla subida (PAN-ING-02).
 *
 * El panel no abre el `.xlsx`: le pregunta al backend, que ya tiene el lector que usa el
 * procesamiento. Meterle un parser de Excel al navegador sería una segunda implementación
 * de algo que ya existe, y las dos se separarían el día que una acepte un formato que la
 * otra no.
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: { params: { vinculoId: string } },
): Promise<NextResponse> {
  return reenviarAlBackend(`/planillas/${params.vinculoId}/encabezados`, "GET");
}
