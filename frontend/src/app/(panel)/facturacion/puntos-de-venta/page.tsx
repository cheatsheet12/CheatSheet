/**
 * PAN-FAC-05 — Facturación · Puntos de venta (HU-E5-05).
 *
 * A server component that fetches and a client component that interacts, like every other
 * listing in the panel. The listing is read here with the session cookie, so the first
 * paint already has rows.
 *
 * The role decides whether the write actions render: HU-E5-05's actor is the
 * Administrador. Hiding them is a courtesy — the use case refuses regardless of what the
 * browser draws, which is what PRU-09 taught.
 *
 * **El encabezado lo dibuja el componente**, como en el listado de comprobantes: el alta
 * vive al lado del título y depende del mismo `puedeEditar` que las tarjetas, así que
 * tenerlos separados sería pasar el rol dos veces por dos caminos que pueden discrepar.
 */

import { redirect } from "next/navigation";

import { PuntosDeVenta } from "@/features/billing";
import type { ListadoDePuntosDeVenta } from "@/features/billing";
import { llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Puntos de venta · CheatSheet" };

export default async function PaginaDePuntosDeVenta(): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  const listado = await llamarApi<ListadoDePuntosDeVenta>("/puntos-de-venta");

  return <PuntosDeVenta inicial={listado} puedeEditar={claims.rol === "ADMINISTRADOR"} />;
}
