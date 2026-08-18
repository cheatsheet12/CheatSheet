/**
 * BFF — the live check of HU-E2-05.
 *
 * `POST` and not `GET` because it has an effect: it calls four external services and
 * writes what it found, including an audit row when a state changed.
 */

import type { NextResponse } from "next/server";

import { reenviarIntegracion } from "@/app/api/integraciones/_proxy";

export const dynamic = "force-dynamic";

export async function POST(): Promise<NextResponse> {
  return reenviarIntegracion("/integraciones/verificacion", "POST");
}
