/**
 * PAN-FAC-01 — Facturación · Listado (HU-E5-01).
 *
 * A server component that fetches and a client component that filters, like every other
 * listing in the panel.
 *
 * The role decides whether «Emitir comprobante» renders: HU-E5-03's actors are the
 * Administrador and the Operador, and RN-04 of HU-E5-01 gives Solo Lectura the right to see
 * and filter without actions. Hiding the button is a courtesy — the use case refuses
 * regardless, which is what PRU-09 taught.
 */

import { redirect } from "next/navigation";

import { ListadoDeComprobantes } from "@/features/billing";
import type { ListadoDeComprobantesRespuesta } from "@/features/billing";
import { llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Facturación · CheatSheet" };

export default async function PaginaDeFacturacion(): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  const listado = await llamarApi<ListadoDeComprobantesRespuesta>("/comprobantes");

  return (
    <>
      <h1>Facturación</h1>
      <p className="dm-intro">
        Los comprobantes que emitiste, con su CAE cuando ARCA los autorizó. Un comprobante
        autorizado no se modifica ni se borra: se anula con una nota de crédito.
      </p>
      <ListadoDeComprobantes
        inicial={listado}
        puedeEmitir={claims.rol === "ADMINISTRADOR" || claims.rol === "OPERADOR"}
      />
    </>
  );
}
