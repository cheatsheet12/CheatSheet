/**
 * PAN-AGE-02 — Agenda · Detalle de turno (HU-E7-02, HU-E7-03).
 *
 * Su propia URL y no un modal sobre la agenda: es la página que alguien deja abierta mientras
 * habla por teléfono con un cliente que quiere cambiar el horario.
 *
 * El nombre del recurso y el del servicio se resuelven del lado del servidor. Un id en una
 * pantalla no le dice nada a quien la mira, y pedirlos desde el componente sería una consulta
 * más por cada turno que alguien abre.
 */

import { notFound, redirect } from "next/navigation";

import { DetalleDeTurno } from "@/features/scheduling";
import type { ListadoDeRecursos, ServicioAgendable, Turno } from "@/features/scheduling";
import { ErrorDeApi, llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Turno · CheatSheet" };

interface Props {
  readonly params: { readonly turnoId: string };
}

export default async function PaginaDeTurno({ params }: Props): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  const turno = await leer(params.turnoId);
  if (turno === null) {
    // Bajo RLS «no es tuyo» y «no existe» son la misma respuesta a propósito: distinguirlas le
    // diría a una empresa que el id de un turno ajeno es real.
    notFound();
  }

  const [recursos, servicios] = await Promise.all([
    llamarApi<ListadoDeRecursos>("/recursos"),
    llamarApi<readonly ServicioAgendable[]>("/recursos/servicios"),
  ]);

  return (
    <>
      <h1>Turno</h1>
      <DetalleDeTurno
        inicial={turno}
        puedeGestionar={claims.rol === "ADMINISTRADOR" || claims.rol === "OPERADOR"}
        recurso={recursos.recursos.find((uno) => uno.id === turno.recurso_id)?.nombre ?? "—"}
        servicio={servicios.find((uno) => uno.id === turno.servicio_id)?.nombre ?? "—"}
      />
    </>
  );
}

async function leer(turnoId: string): Promise<Turno | null> {
  try {
    return await llamarApi<Turno>(`/turnos/${turnoId}`);
  } catch (error) {
    if (error instanceof ErrorDeApi && error.status < 500) {
      return null;
    }
    throw error;
  }
}
