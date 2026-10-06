/**
 * PAN-AGE-02 — Agenda · Nuevo turno (HU-E7-06).
 *
 * **Solo Lectura no llega acá.** El caso de uso lo rechaza igual, pero renderizarle el
 * formulario entero para contestarle 403 en «Reservar» le hace perder la tarde a alguien.
 *
 * El cliente se elige antes, como en la emisión y en el cobro: es el dato que decide para
 * quién es el turno, y un selector más en este formulario lo haría más largo sin hacerlo más
 * claro.
 */

import Link from "next/link";
import { redirect } from "next/navigation";

import { NuevoTurno } from "@/features/scheduling";
import type { ListadoDeRecursos, ServicioAgendable } from "@/features/scheduling";
import { llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Nuevo turno · CheatSheet" };

interface Props {
  readonly searchParams: { readonly cliente?: string };
}

export default async function PaginaDeNuevoTurno({ searchParams }: Props): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }
  if (claims.rol !== "ADMINISTRADOR" && claims.rol !== "OPERADOR") {
    redirect("/agenda");
  }

  const clienteId = searchParams.cliente;
  if (clienteId === undefined) {
    return (
      <div className="age-pantalla">
        <div className="age-encabezado">
          <div>
            <p className="age-encabezado__eyebrow">Operaciones · Agenda</p>
            <h1 className="age-encabezado__titulo">Nuevo turno</h1>
            <p className="age-encabezado__intro">
              Elegí primero para quién es el turno.{" "}
              <Link href="/datos-maestros/clientes">Ir a Clientes</Link>.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const [recursos, servicios] = await Promise.all([
    llamarApi<ListadoDeRecursos>("/recursos?solo_activos=true"),
    llamarApi<readonly ServicioAgendable[]>("/recursos/servicios"),
  ]);

  return (
    <div className="age-pantalla">
      <div className="age-encabezado">
        <div>
          <p className="age-encabezado__eyebrow">Operaciones · Agenda</p>
          <h1 className="age-encabezado__titulo">Nuevo turno</h1>
          <p className="age-encabezado__intro">
            El horario se elige de los que el recurso ofrece ese día. Si alguien se adelanta entre
            que elegís y confirmás, el sistema te lo va a decir.
          </p>
        </div>
        <div className="age-encabezado__acciones">
          <Link className="age-volver" href="/agenda">
            Volver a la agenda
          </Link>
        </div>
      </div>
      <NuevoTurno
        clienteId={clienteId}
        recursos={recursos.recursos}
        servicios={servicios}
        puedeRegistrarAPosteriori={claims.rol === "ADMINISTRADOR"}
      />
    </div>
  );
}
