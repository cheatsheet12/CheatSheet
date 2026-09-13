/**
 * PAN-COB-01 — Cobros · Listado (HU-E6-01).
 *
 * Un componente de servidor que trae y uno de cliente que filtra, como todos los listados del
 * panel. El rol decide si aparece «Generar cobro»: HU-E6-01 RN-04 le da a Solo Lectura el
 * derecho a ver y filtrar sin acciones.
 */

import { redirect } from "next/navigation";

import { ListadoDeCobros } from "@/features/payments";
import type { ListadoDeCobrosRespuesta } from "@/features/payments";
import { llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Cobros · CheatSheet" };

export default async function PaginaDeCobros(): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  const listado = await llamarApi<ListadoDeCobrosRespuesta>("/cobros");

  return (
    <>
      <h1>Cobros</h1>
      <p className="dm-intro">
        Lo cobrado, lo pendiente y lo que está en mora, con la cadena de recordatorios corriendo
        sola según la regla que configuraste.
      </p>
      <ListadoDeCobros
        inicial={listado}
        puedeGestionar={claims.rol === "ADMINISTRADOR" || claims.rol === "OPERADOR"}
      />
    </>
  );
}
