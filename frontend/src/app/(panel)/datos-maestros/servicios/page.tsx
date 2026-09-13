/**
 * PAN-DM-02 — Datos Maestros · Servicios (HU-E4-02).
 *
 * A server component that fetches and a client component that interacts, like PAN-DM-01.
 * Same hueco P10 as its sibling: the Etapa 5 navigation map codes this screen and grades
 * its roles, but never mocked it up, so it is built from the component catalogue of the
 * specification §1.3.
 *
 * The role decides whether the write actions render. Hiding them is a courtesy — the
 * backend refuses regardless.
 *
 * **El encabezado lo dibuja el componente**, por la misma razón que en PAN-DM-01: el CTA
 * depende del rol y abre el formulario, así que título y acción son una sola pieza.
 */

import { redirect } from "next/navigation";

import { ListadoDeServicios } from "@/features/master_data";
import type { ListadoDeServiciosRespuesta } from "@/features/master_data";
import { llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Servicios · CheatSheet" };

const ROLES_QUE_ESCRIBEN = ["ADMINISTRADOR", "OPERADOR"];

export default async function PaginaDeServicios(): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  const listado = await llamarApi<ListadoDeServiciosRespuesta>("/servicios");

  return (
    <ListadoDeServicios inicial={listado} puedeEditar={ROLES_QUE_ESCRIBEN.includes(claims.rol)} />
  );
}
