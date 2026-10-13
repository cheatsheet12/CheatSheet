/**
 * `/aceptacion-legal` — a variant of PAN-ONB-01 for whoever owes a legal document
 * (HU-E1-03 RN-03, HU-E1-08 RN-05; decision 8 of the unit plan).
 *
 * It lives in `(alta)` and not in `(panel)` for the same reason the onboarding does: the
 * person has a session but, until they accept, no panel. The `(panel)` layout would send them
 * straight back here.
 *
 * What is pending is asked of the API every time (`GET /legal/pendientes` is one of the three
 * routes it answers while something is owed). Nothing pending means there is nothing to do
 * here, and the person goes to the panel: a bookmarked or back-button visit never shows an
 * empty screen.
 */

import { redirect } from "next/navigation";

import { FormularioDeReaceptacion } from "@/features/identity";
import type { PendienteLegal, PendientesLegales } from "@/features/identity";
import { ErrorDeApi, llamarApi } from "@/lib/api";
import { haySesion } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Textos legales · CheatSheet",
  robots: { index: false, follow: false },
};

export default async function PaginaDeAceptacionLegal(): Promise<JSX.Element> {
  if (!haySesion()) {
    // The access cookie lasts fifteen minutes; renewing keeps somebody who comes back after a
    // pause from landing on the login, and brings them back here.
    redirect("/api/auth/renovar?destino=/aceptacion-legal");
  }

  const pendientes = await leerPendientes();
  if (pendientes === null) {
    redirect("/");
  }
  if (pendientes.length === 0) {
    redirect("/panel");
  }
  return <FormularioDeReaceptacion pendientes={pendientes} />;
}

/** `null` when the API rejected the session (expired or revoked); anything else is an outage. */
async function leerPendientes(): Promise<readonly PendienteLegal[] | null> {
  try {
    return (await llamarApi<PendientesLegales>("/legal/pendientes")).pendientes;
  } catch (error) {
    if (error instanceof ErrorDeApi && error.status < 500) {
      return null;
    }
    throw error;
  }
}
