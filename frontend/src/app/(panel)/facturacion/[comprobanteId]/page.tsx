/**
 * PAN-FAC-02 — Facturación · Detalle (HU-E5-02).
 *
 * Its own URL rather than a modal over the listing, and that is deliberate: this is the
 * page somebody sends to their accountant, opens in a second tab next to a paper invoice,
 * and bookmarks. A modal has none of those.
 *
 * Every role reads it. There are no actions here at all, so nothing depends on the role.
 */

import { notFound, redirect } from "next/navigation";

import { DetalleDeComprobante } from "@/features/billing";
import type { Comprobante, ListadoDePuntosDeVenta } from "@/features/billing";
import { ErrorDeApi, llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Comprobante · CheatSheet" };

interface Props {
  readonly params: { readonly comprobanteId: string };
}

export default async function PaginaDeComprobante({ params }: Props): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  const comprobante = await leer(params.comprobanteId);
  if (comprobante === null) {
    // Under RLS "not yours" and "does not exist" are the same answer on purpose, and a 404
    // is how that reaches the browser without confirming somebody else's document id.
    notFound();
  }

  // The point of sale's own number, for the `0001-00000123` form ARCA prints. Read
  // separately because the document stores the id and ARCA prints the number.
  const puntos = await llamarApi<ListadoDePuntosDeVenta>("/puntos-de-venta");
  const punto = puntos.puntos.find((uno) => uno.id === comprobante.punto_de_venta_id);

  return (
    <>
      <h1>Comprobante</h1>
      <DetalleDeComprobante comprobante={comprobante} puntoNumero={punto?.numero ?? null} />
    </>
  );
}

async function leer(comprobanteId: string): Promise<Comprobante | null> {
  try {
    return await llamarApi<Comprobante>(`/comprobantes/${comprobanteId}`);
  } catch (error) {
    if (error instanceof ErrorDeApi && error.status < 500) {
      return null;
    }
    throw error;
  }
}
