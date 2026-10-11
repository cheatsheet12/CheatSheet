/**
 * BFF — la agenda de notificación: cuántas horas antes del turno se recuerda (HU-E11-01).
 *
 * `PUT` y no `POST` porque **reemplaza**: una empresa tiene una agenda, no un catálogo.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function PUT(request: Request): Promise<NextResponse> {
  return reenviarAlBackend("/reglas/agenda", "PUT", await cuerpoDe(request));
}
