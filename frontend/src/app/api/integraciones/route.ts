/**
 * BFF — the company's integrations (PAN-CFG-INT).
 *
 * Readable by Administrador and Operador: HU-E2-05 names both actors. Which of them may
 * *connect* is decided by the backend, not here.
 */

import type { NextResponse } from "next/server";

import { reenviarIntegracion } from "@/app/api/integraciones/_proxy";

export const dynamic = "force-dynamic";

export async function GET(): Promise<NextResponse> {
  return reenviarIntegracion("/integraciones", "GET");
}
