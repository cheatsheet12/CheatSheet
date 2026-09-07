/**
 * PAN-ING-03 — el detalle de un procesamiento (HU-E3-05).
 *
 * Servidor que lee, cliente que interactúa, como las otras pantallas del panel. El rol no
 * se mapea acá: `puede_reprocesar` viene del backend, que ya contempla las dos razones por
 * las que no se puede — Solo Lectura (RN-04), o ninguna fila que corregir.
 */

import { redirect } from "next/navigation";

import { DetalleDeCarga } from "@/features/spreadsheet_sync";
// El tipo y el componente comparten nombre en el dominio; el barrel expone el tipo con
// sufijo para que una ruta pueda usar los dos.
import type { DetalleDeCargaRespuesta } from "@/features/spreadsheet_sync";
import { llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Detalle de carga · CheatSheet" };

export default async function PaginaDeCarga({
  params,
}: {
  params: { cargaId: string };
}): Promise<JSX.Element> {
  if (leerClaims() === null) {
    redirect("/");
  }

  const detalle = await llamarApi<DetalleDeCargaRespuesta>(`/planillas/cargas/${params.cargaId}`);

  return (
    <>
      <h1>Detalle de la carga</h1>
      <p className="dm-intro">
        Qué entró, qué no, y por qué. Podés corregir las filas en tu planilla y reprocesar sólo
        esas.
      </p>
      <DetalleDeCarga inicial={detalle} />
    </>
  );
}
