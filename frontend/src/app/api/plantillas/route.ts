/**
 * BFF — las plantillas de notificación (PAN-CFG-NOT).
 *
 * **Sólo `GET`.** No hay alta ni baja: los códigos los define el sistema, y el backend siembra
 * las que falten la primera vez que se piden. Lo que un administrador hace es editar el cuerpo.
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(): Promise<NextResponse> {
  return reenviarAlBackend("/plantillas", "GET");
}
