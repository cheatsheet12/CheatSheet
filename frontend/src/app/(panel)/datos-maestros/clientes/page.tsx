/**
 * PAN-DM-01 — Datos Maestros · Clientes (HU-E4-01).
 *
 * A server component that fetches and a client component that interacts, like PAN-USR-01
 * and PAN-CFG-INT. The first page of the catalogue is read here with the session cookie,
 * so the first paint already has rows instead of a spinner that resolves into the same
 * thing.
 *
 * **This screen has no prototype** (hueco P10 of the epic 3 units map). The Etapa 5
 * navigation map codes it and grades its roles, but never mocked it up. It is built from
 * the component catalogue of the specification §1.3, exactly as PAN-USR-01 was under the
 * same circumstances.
 *
 * The role decides whether the write actions render: the navigation map §5 grades Datos
 * Maestros **Admin ● · Operador ● · Solo Lectura RO**. Hiding them is a courtesy, not the
 * guard — the backend refuses regardless.
 */

import { redirect } from "next/navigation";

import { ListadoDeClientes } from "@/features/master_data";
import type { ListadoDeClientesRespuesta } from "@/features/master_data";
import { llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Clientes · CheatSheet" };

const ROLES_QUE_ESCRIBEN = ["ADMINISTRADOR", "OPERADOR"];

export default async function PaginaDeClientes(): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  const listado = await llamarApi<ListadoDeClientesRespuesta>("/clientes");

  return (
    <>
      <header className="dm-encabezado">
        <div>
          <span className="dm-encabezado__cintillo">Datos maestros</span>
          <h1>Clientes</h1>
          <p className="dm-intro">
            El catalogo de clientes de tu empresa. Lo que crees aca queda disponible para
            facturacion, cobros y agenda.
          </p>
        </div>
      </header>
      <ListadoDeClientes inicial={listado} puedeEditar={ROLES_QUE_ESCRIBEN.includes(claims.rol)} />
    </>
  );
}
