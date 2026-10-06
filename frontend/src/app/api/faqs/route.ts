/**
 * BFF — las respuestas frecuentes del agente (PAN-WA-02).
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(): Promise<NextResponse> {
  return reenviarAlBackend("/faqs", "GET");
}

export async function POST(request: Request): Promise<NextResponse> {
  return reenviarAlBackend("/faqs", "POST", await cuerpoDe(request));
}
