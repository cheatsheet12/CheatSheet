/**
 * PAN-AGE-01 — Agenda · Vista de turnos (HU-E7-01).
 *
 * Los recursos se traen acá y no en el componente porque el filtro por recurso los necesita
 * para su primer render: pedirlos del lado del cliente haría que el selector apareciera vacío
 * el primer segundo, justo cuando alguien está buscando el recurso que vino a mirar.
 */

import { redirect } from "next/navigation";

import { AgendaDelDia } from "@/features/scheduling";
import type { ListadoDeRecursos, ListadoDeTurnos } from "@/features/scheduling";
import { llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Agenda · CheatSheet" };

export default async function PaginaDeAgenda(): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  const [turnos, recursos] = await Promise.all([
    llamarApi<ListadoDeTurnos>("/turnos"),
    llamarApi<ListadoDeRecursos>("/recursos"),
  ]);

  return (
    <>
      <h1>Agenda</h1>
      <p className="dm-intro">
        Los turnos del día en curso. Cambiá el rango o el recurso para ver otra cosa; un turno
        reprogramado aparece en su franja nueva conservando su estado.
      </p>
      <AgendaDelDia
        inicial={turnos}
        recursos={recursos.recursos}
        puedeGestionar={claims.rol === "ADMINISTRADOR" || claims.rol === "OPERADOR"}
      />
    </>
  );
}
