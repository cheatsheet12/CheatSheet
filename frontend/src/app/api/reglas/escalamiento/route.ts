/**
 * BFF — la cadena de recordatorios de cobro (HU-E11-01 RN-02).
 *
 * `PUT` y no `POST` porque **reemplaza**: una empresa tiene una cadena de escalamiento, no un
 * catálogo de cadenas.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function PUT(request: Request): Promise<NextResponse> {
  return reenviarAlBackend("/reglas/escalamiento", "PUT", await cuerpoDe(request));
}
