/**
 * PAN-FAC-04 — Facturación · Nueva nota de crédito (HU-E5-04).
 *
 * The two preconditions of the story are checked here, before the form renders, because
 * each has a different answer: Solo Lectura is sent back — the use case refuses it anyway,
 * and rendering a whole form to answer 403 on Submit wastes somebody's afternoon — and a
 * document ARCA has not authorised cannot be reversed at all.
 */

import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { AnularComprobante } from "@/features/billing";
import type { Anulacion, Comprobante } from "@/features/billing";
import { ErrorDeApi, llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Nota de crédito · CheatSheet" };

interface Props {
  readonly params: { readonly comprobanteId: string };
}

export default async function PaginaDeAnulacion({ params }: Props): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }
  if (claims.rol !== "ADMINISTRADOR" && claims.rol !== "OPERADOR") {
    redirect(`/facturacion/${params.comprobanteId}`);
  }

  const original = await leer(params.comprobanteId);
  if (original === null) {
    notFound();
  }

  if (original.estado !== "AUTORIZADO") {
    // RN-01. Said as a reason and not as a refusal: what somebody does next depends on
    // *why* — a rejected document is fixed and reissued, one in flight is waited on.
    return (
      <>
        <h1>Nota de crédito</h1>
        <p className="dm-intro">
          Sólo se puede anular un comprobante que ARCA autorizó, y éste todavía no lo está.{" "}
          <Link href={`/facturacion/${original.id}`}>Volver al comprobante</Link>.
        </p>
      </>
    );
  }

  const anulacion = await llamarApi<Anulacion>(`/comprobantes/${original.id}/anulacion`);

  return (
    <>
      <h1>Nota de crédito</h1>
      <p className="dm-intro">
        Una nota de crédito también va a ARCA y también queda: es la forma de reversar una factura,
        no de borrarla.
      </p>
      <AnularComprobante original={original} anulacion={anulacion} />
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
