/**
 * PAN-AGE-02 — Agenda · Detalle de turno (HU-E7-02, HU-E7-03).
 *
 * Su propia URL y no un modal sobre la agenda: es la página que alguien deja abierta mientras
 * habla por teléfono con un cliente que quiere cambiar el horario.
 *
 * El nombre del recurso, el del servicio y los datos del cliente se resuelven del lado del
 * servidor. Un id en una pantalla no le dice nada a quien la mira, y pedirlos desde el
 * componente sería una consulta más por cada turno que alguien abre.
 */

import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import type { Cliente } from "@/features/master_data";
import { DetalleDeTurno } from "@/features/scheduling";
import type {
  ClienteDelTurno,
  ListadoDeRecursos,
  ServicioAgendable,
  Turno,
} from "@/features/scheduling";
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

  const [recursos, servicios, cliente] = await Promise.all([
    llamarApi<ListadoDeRecursos>("/recursos"),
    llamarApi<readonly ServicioAgendable[]>("/recursos/servicios"),
    leerCliente(turno.cliente_id),
  ]);

  return (
    <div className="age-pantalla">
      <div className="age-encabezado">
        <div>
          <p className="age-encabezado__eyebrow">Operaciones · Agenda</p>
          <h1 className="age-encabezado__titulo">Turno</h1>
          <p className="age-encabezado__intro">
            El turno, con las acciones que su estado permite. Reprogramarlo lo mueve de franja y le
            deja el estado que tenía.
          </p>
        </div>
        <div className="age-encabezado__acciones">
          <Link className="age-volver" href="/agenda">
            Volver a la agenda
          </Link>
        </div>
      </div>
      <DetalleDeTurno
        inicial={turno}
        puedeGestionar={claims.rol === "ADMINISTRADOR" || claims.rol === "OPERADOR"}
        recurso={recursos.recursos.find((uno) => uno.id === turno.recurso_id)?.nombre ?? "—"}
        servicio={servicios.find((uno) => uno.id === turno.servicio_id)?.nombre ?? "—"}
        cliente={cliente}
        puedeRegistrarAPosteriori={claims.rol === "ADMINISTRADOR"}
      />
    </div>
  );
}

/**
 * El cliente del turno (#167), o `null` si la API no lo devolvió.
 *
 * Una respuesta de error de la API —cualquier código— deja la página en pie: el turno es lo
 * que se vino a ver, y sin el cliente se lo puede seguir cancelando o reprogramando. El
 * componente muestra «—» en cada dato.
 */
async function leerCliente(clienteId: string): Promise<ClienteDelTurno | null> {
  try {
    const cliente = await llamarApi<Cliente>(`/clientes/${clienteId}`);
    return {
      nombre: cliente.nombre,
      cuit: cliente.cuit,
      contacto_whatsapp: cliente.contacto_whatsapp,
      contacto_email: cliente.contacto_email,
    };
  } catch (error) {
    if (error instanceof ErrorDeApi) {
      return null;
    }
    throw error;
  }
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
