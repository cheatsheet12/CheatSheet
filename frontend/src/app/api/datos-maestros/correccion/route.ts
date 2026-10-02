/** BFF — apply the correction of existing data (PAN-DM-01). Administrador only, in the backend. */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function POST(): Promise<NextResponse> {
  return reenviarAlBackend("/datos-maestros/correccion", "POST");
}
