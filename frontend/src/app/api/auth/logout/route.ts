/**
 * BFF — sign out.
 *
 * The cookies are cleared **whatever the backend answers**. If the revocation call fails,
 * the honest thing is still to end the session in this browser: leaving somebody logged
 * in because a network call failed is the opposite of what they asked for. The refresh
 * token is revoked server-side on a best-effort basis, and its family with it.
 */

import { NextResponse } from "next/server";

import { llamarApi } from "@/lib/api";
import { cerrarSesion } from "@/lib/session";

import { borrarRefresh, leerRefresh } from "@/app/api/auth/_sesion";

export const dynamic = "force-dynamic";

export async function POST(): Promise<NextResponse> {
  const refresh = leerRefresh();
  if (refresh !== undefined) {
    try {
      await llamarApi<unknown>("/auth/logout", {
        method: "POST",
        body: { refresh_token: refresh },
      });
    } catch {
      // Deliberately swallowed: see the note above.
    }
  }
  cerrarSesion();
  borrarRefresh();
  return NextResponse.json({ cerrada: true });
}
