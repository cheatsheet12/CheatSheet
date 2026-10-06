/**
 * BFF — el acceso del contador externo (PAN-REP-02, HU-E10-05).
 *
 * **La respuesta no lleva el enlace.** El backend no lo devuelve y esta ruta no lo inventa: el
 * enlace existe una sola vez, en el correo que sale. Devolvérselo al administrador lo dejaría
 * en el historial del navegador y en cualquier log del camino.
 *
 * El `DELETE` de acá **no borra nada**: revoca. La fila queda, con sus accesos, que es lo que
 * hace auditable un acceso sin cuenta (HU-E10-06 RN-03).
 */

import type { NextResponse } from "next/server";

import { cuerpoDe, reenviarAlBackend } from "@/app/api/usuarios/_proxy";

export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<NextResponse> {
  return reenviarAlBackend("/reporteria/contador", "POST", await cuerpoDe(request));
}

export async function DELETE(): Promise<NextResponse> {
  return reenviarAlBackend("/reporteria/contador", "DELETE");
}
