/**
 * PAN-AGE-01 — Agenda · Vista de turnos (HU-E7-01).
 *
 * Las cuatro lecturas se hacen acá, del lado del servidor, y no en el componente:
 *
 * - los **recursos** los necesita el filtro por recurso para su primer render — pedirlos desde
 *   el navegador haría que el selector apareciera vacío el primer segundo, justo cuando alguien
 *   está buscando el recurso que vino a mirar;
 * - los **clientes** y los **servicios** son los nombres de las dos columnas que la fila
 *   muestra. Un `Turno` viaja con ids, y un UUID en una agenda no le dice nada a quien la mira.
 *
 * Van en un `Promise.all` porque son independientes: en serie, la pantalla tardaría la suma de
 * las cuatro.
 *
 * **El «ahora» del cintillo también sale de acá.** Es un componente de cliente el que lo pinta,
 * y Next lo renderiza primero en el servidor: si cada lado llamara a `new Date()`, un turno
 * abierto a las 23:59:59 podría escribir dos días distintos y React descartaría el HTML.
 */

import { redirect } from "next/navigation";

import type { ListadoDeClientesRespuesta } from "@/features/master_data";
import { AgendaDelDia } from "@/features/scheduling";
import type { ListadoDeRecursos, ListadoDeTurnos, ServicioAgendable } from "@/features/scheduling";
import { llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Agenda · CheatSheet" };

export default async function PaginaDeAgenda(): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  const [turnos, recursos, servicios, clientes] = await Promise.all([
    llamarApi<ListadoDeTurnos>("/turnos"),
    llamarApi<ListadoDeRecursos>("/recursos"),
    llamarApi<readonly ServicioAgendable[]>("/recursos/servicios"),
    llamarApi<ListadoDeClientesRespuesta>("/clientes"),
  ]);

  return (
    <AgendaDelDia
      inicial={turnos}
      recursos={recursos.recursos}
      servicios={servicios}
      clientes={clientes.clientes}
      hoy={new Date().toISOString()}
      puedeGestionar={claims.rol === "ADMINISTRADOR" || claims.rol === "OPERADOR"}
    />
  );
}
