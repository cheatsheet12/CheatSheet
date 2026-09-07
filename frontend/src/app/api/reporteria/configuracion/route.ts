/**
 * BFF — la configuración del envío automático (PAN-REP-02, HU-E10-04).
 *
 * `PUT` con la configuración entera y no una serie de `PATCH`: la pantalla es un formulario
 * con un botón, y partirlo dejaría estados intermedios donde el envío quedó activo con un día
 * que el usuario todavía no confirmó.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(): Promise<NextResponse> {
  return reenviarAlBackend("/reporteria/configuracion", "GET");
}

export async function PUT(request: Request): Promise<NextResponse> {
  return reenviarAlBackend("/reporteria/configuracion", "PUT", await cuerpoDe(request));
}
