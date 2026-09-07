/**
 * PAN-COB-02 — Cobros · Detalle (HU-E6-02, HU-E6-04, HU-E6-05).
 *
 * Su propia URL y no un modal sobre el listado: es la página que alguien deja abierta mientras
 * habla por teléfono con un cliente, y la que manda por mensaje interno cuando pregunta si un
 * pago entró.
 *
 * Todos los roles la leen. El reembolso es sólo del Administrador (RN-05) y la cancelación
 * también del Operador; el caso de uso los refuerza.
 */

import { notFound, redirect } from "next/navigation";

import { DetalleDeCobro } from "@/features/payments";
import type { DetalleDeCobroRespuesta } from "@/features/payments";
import { ErrorDeApi, llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Cobro · CheatSheet" };

interface Props {
  readonly params: { readonly cobroId: string };
}

export default async function PaginaDeCobro({ params }: Props): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  const cobro = await leer(params.cobroId);
  if (cobro === null) {
    // Bajo RLS «no es tuyo» y «no existe» son la misma respuesta a propósito: distinguirlas le
    // diría a una empresa que el id de un cobro ajeno es real.
    notFound();
  }

  return (
    <>
      <h1>Cobro</h1>
      <DetalleDeCobro
        inicial={cobro}
        puedeGestionar={claims.rol === "ADMINISTRADOR" || claims.rol === "OPERADOR"}
        puedeReembolsar={claims.rol === "ADMINISTRADOR"}
      />
    </>
  );
}

async function leer(cobroId: string): Promise<DetalleDeCobroRespuesta | null> {
  try {
    return await llamarApi<DetalleDeCobroRespuesta>(`/cobros/${cobroId}`);
  } catch (error) {
    if (error instanceof ErrorDeApi && error.status < 500) {
      return null;
    }
    throw error;
  }
}
