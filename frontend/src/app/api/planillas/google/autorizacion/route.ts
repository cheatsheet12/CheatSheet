/**
 * BFF — where the user goes to grant read access to one spreadsheet (HU-E2-04 RN-01).
 *
 * The backend sets the `state` cookie on its own response; this handler forwards the URL
 * and nothing else. The cookie rides back to the browser through the proxy's response
 * because it is set on the same origin the panel is served from.
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function POST(): Promise<NextResponse> {
  return reenviarAlBackend("/planillas/google/autorizacion", "POST");
}
