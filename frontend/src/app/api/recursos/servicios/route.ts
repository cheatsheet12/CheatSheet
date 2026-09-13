/**
 * BFF — los servicios que se pueden reservar (HU-E7-04 RN-02).
 *
 * Vive bajo `/recursos` y no bajo `/servicios` a propósito: el catálogo completo es de
 * `master_data` y ya tiene su ruta; esto es la vista que la agenda necesita, filtrada por una
 * regla de este épico — agendable, activo y con duración.
 */

import type { NextResponse } from "next/server";

import { reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function GET(): Promise<NextResponse> {
  return reenviarAlBackend("/recursos/servicios", "GET");
}
