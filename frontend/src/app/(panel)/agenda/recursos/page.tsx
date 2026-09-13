/**
 * PAN-AGE-03 — Agenda · Configuración de recursos (HU-E7-04, HU-E7-05).
 *
 * Todos los roles ven el listado con nombre, tipo, servicios y estado, que es lo que pide el
 * primer criterio. Sólo el Administrador configura, y el caso de uso lo refuerza.
 */

import { redirect } from "next/navigation";

import { RecursosReservables } from "@/features/scheduling";
import type { ListadoDeRecursos, ServicioAgendable } from "@/features/scheduling";
import { llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Recursos · CheatSheet" };

export default async function PaginaDeRecursos(): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  const [recursos, servicios] = await Promise.all([
    llamarApi<ListadoDeRecursos>("/recursos"),
    llamarApi<readonly ServicioAgendable[]>("/recursos/servicios"),
  ]);

  return (
    <>
      <h1>Recursos reservables</h1>
      <p className="dm-intro">
        Una persona, un espacio o un equipo, con el horario en el que atiende y los servicios que se
        prestan en él. Sin al menos uno activo no se pueden reservar turnos.
      </p>
      <RecursosReservables
        inicial={recursos}
        servicios={servicios}
        puedeEditar={claims.rol === "ADMINISTRADOR"}
      />
    </>
  );
}
