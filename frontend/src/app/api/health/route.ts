/**
 * The first BFF route handler, and the proof that the pattern works end to end.
 *
 * The browser asks *this* app whether the system is healthy; this app asks the API.
 * The backend's URL never reaches the client, and neither does the session cookie's
 * value — which is the arrangement every future feature route reuses.
 */

import { NextResponse } from "next/server";

import { ErrorDeApi, llamarApi } from "@/lib/api";

interface SaludDelBackend {
  readonly estado: "ok" | "degradado";
  readonly base_de_datos: boolean;
  readonly redis: boolean;
}

export const dynamic = "force-dynamic";

export async function GET(): Promise<NextResponse> {
  try {
    const salud = await llamarApi<SaludDelBackend>("/health", { timeoutMs: 3000 });
    return NextResponse.json({ estado: salud.estado, api: true });
  } catch (error) {
    // What the client is told is that the API is unreachable — never why, and never
    // where it lives.
    const status = error instanceof ErrorDeApi ? 503 : 500;
    return NextResponse.json({ estado: "degradado", api: false }, { status });
  }
}
