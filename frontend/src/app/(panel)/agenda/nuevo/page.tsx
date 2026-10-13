/**
 * PAN-AGE-02 — Agenda · Nuevo turno (HU-E7-06).
 *
 * **Solo Lectura no llega acá.** El caso de uso lo rechaza igual, pero renderizarle el
 * formulario entero para contestarle 403 en «Reservar» le hace perder la tarde a alguien.
 *
 * **La página compone y la URL decide**, igual que en Nuevo cobro. El selector de clientes es
 * de `master_data` y el formulario de `scheduling`; ninguno importa al otro (R5), así que quien
 * los junta es esta ruta. El cliente elegido vive en `?cliente=<id>`: elegir a otro navega acá
 * mismo y la página se vuelve a renderizar en el servidor con ese cliente. Sin cliente el
 * formulario se muestra igual y «Reservar» queda deshabilitado; antes, «Nuevo turno» terminaba
 * en una tarjeta cuya única salida era irse a Clientes.
 *
 * El formulario dice para quién es el turno (#167): el nombre se resuelve acá, del lado del
 * servidor.
 */

import Link from "next/link";
import { redirect } from "next/navigation";

import { SelectorDeClientes } from "@/features/master_data";
import type { Cliente } from "@/features/master_data";
import { NuevoTurno } from "@/features/scheduling";
import type { ListadoDeRecursos, ServicioAgendable } from "@/features/scheduling";
import { Alert } from "@/shared";
import { ErrorDeApi, llamarApi } from "@/lib/api";
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

  const [recursos, servicios, { cliente, indicadoPeroInvalido }] = await Promise.all([
    llamarApi<ListadoDeRecursos>("/recursos?solo_activos=true"),
    llamarApi<readonly ServicioAgendable[]>("/recursos/servicios"),
    cargarCliente(searchParams.cliente),
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
      {indicadoPeroInvalido && (
        <Alert tono="advertencia">El cliente indicado no existe o está inactivo.</Alert>
      )}
      <SelectorDeClientes
        destino="/agenda/nuevo"
        seleccionado={
          cliente === null ? null : { id: cliente.id, nombre: cliente.nombre, cuit: cliente.cuit }
        }
      />
      <NuevoTurno
        clienteId={cliente?.id ?? null}
        clienteNombre={cliente?.nombre ?? null}
        recursos={recursos.recursos}
        servicios={servicios}
        puedeRegistrarAPosteriori={claims.rol === "ADMINISTRADOR"}
      />
    </div>
  );
}

/**
 * El cliente de `?cliente=`, si existe y está activo. Un id viejo, ajeno o de alguien dado de
 * baja se trata como «sin cliente» y se avisa, igual que en Nuevo cobro. Un fallo que no es
 * «no existe» sí se deja subir: disfrazar una caída del backend de «cliente vacío» esconde el
 * problema.
 */
async function cargarCliente(
  id: string | undefined,
): Promise<{ cliente: Cliente | null; indicadoPeroInvalido: boolean }> {
  if (id === undefined) {
    return { cliente: null, indicadoPeroInvalido: false };
  }
  try {
    const cliente = await llamarApi<Cliente>(`/clientes/${encodeURIComponent(id)}`);
    return cliente.activo
      ? { cliente, indicadoPeroInvalido: false }
      : { cliente: null, indicadoPeroInvalido: true };
  } catch (fallo) {
    // 422 es «no existe» (o un id mal formado); 404 lo cubre si el backend algún día lo cambia.
    if (fallo instanceof ErrorDeApi && (fallo.status === 404 || fallo.status === 422)) {
      return { cliente: null, indicadoPeroInvalido: true };
    }
    throw fallo;
  }
}
