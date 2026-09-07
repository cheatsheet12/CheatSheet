/**
 * BFF — las reglas de negocio de la empresa (PAN-CFG-RN).
 *
 * **No hay `DELETE`.** RN-04 pide desactivar: una regla borrada deja la bitácora apuntando a
 * algo que ya no existe.
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(): Promise<NextResponse> {
  return reenviarAlBackend("/reglas", "GET");
}
