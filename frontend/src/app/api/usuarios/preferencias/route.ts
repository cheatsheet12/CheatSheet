/**
 * BFF — the caller's own preferences (HU-E1-07).
 *
 * `/usuarios/yo/...` on the backend: there is no user id in the path, because a path
 * that accepted one would be a path for editing somebody else's settings.
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(): Promise<NextResponse> {
  return reenviarAlBackend("/usuarios/yo/preferencias", "GET");
}

export async function PUT(request: Request): Promise<NextResponse> {
  return reenviarAlBackend("/usuarios/yo/preferencias", "PUT", await cuerpoDe(request));
}
