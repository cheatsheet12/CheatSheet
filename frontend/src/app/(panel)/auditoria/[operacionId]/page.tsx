/**
 * PAN-LOG-02 — Log de Operaciones · Detalle (HU-E12-02).
 */

import Link from "next/link";
import { redirect } from "next/navigation";

import { DetalleDeOperacion } from "@/features/observability";
import type { DetalleDeOperacionRespuesta } from "@/features/observability";
import { ErrorDeApi, llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Detalle de la operación · CheatSheet" };

interface Props {
  readonly params: { readonly operacionId: string };
}

export default async function PaginaDeDetalle({ params }: Props): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  let detalle: DetalleDeOperacionRespuesta | null = null;
  let motivo: string | undefined;
  try {
    detalle = await llamarApi<DetalleDeOperacionRespuesta>(`/bitacora/${params.operacionId}`);
  } catch (error) {
    if (!(error instanceof ErrorDeApi) || error.status >= 500) {
      throw error;
    }
    motivo = error.detalle;
  }

  return (
    <>
      <p className="dm-intro">
        <Link href="/auditoria">← Volver al log</Link>
      </p>
      <h1>Detalle de la operación</h1>
      {detalle === null ? (
        <p className="tabla__vacia">{motivo ?? "La operación no existe."}</p>
      ) : (
        <DetalleDeOperacion detalle={detalle} />
      )}
    </>
  );
}
