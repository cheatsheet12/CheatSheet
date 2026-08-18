/**
 * BFF — the company's users (PAN-USR-01).
 *
 * Readable by any role: HU-E1-05's third criterion has an Operador looking at this list
 * and finding the actions unavailable. What they may *do* is decided by the backend.
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(): Promise<NextResponse> {
  return reenviarAlBackend("/usuarios", "GET");
}
