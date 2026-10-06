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
 *
 * **El encabezado lo dibuja el componente**, y no esta página como en el resto del panel:
 * el CTA verde vive al lado del título y depende del mismo `puedeEmitir` que el listado, así
 * que tenerlos separados sería pasar el rol dos veces por dos caminos que pueden discrepar.
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
    <ListadoDeComprobantes
      inicial={listado}
      puedeEmitir={claims.rol === "ADMINISTRADOR" || claims.rol === "OPERADOR"}
    />
  );
}
