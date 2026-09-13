/**
 * PAN-CFG-NOT — Configuración · Plantillas (HU-E11-02).
 *
 * El listado se pide siempre: el backend siembra las plantillas de fábrica que falten la
 * primera vez que una empresa entra acá.
 */

import { redirect } from "next/navigation";

import { PlantillasDeNotificacion } from "@/features/conversational";
import type { ListadoDePlantillas } from "@/features/conversational";
import { llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Plantillas · CheatSheet" };

export default async function PaginaDePlantillas(): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  const listado = await llamarApi<ListadoDePlantillas>("/plantillas");

  return (
    <>
      <h1>Plantillas de notificación</h1>
      <p className="dm-intro">
        Los mensajes que el sistema manda a tus clientes. Podés editar el texto y usar las variables
        que cada uno admite; el sistema las reemplaza al enviar.
      </p>
      <PlantillasDeNotificacion inicial={listado} puedeEditar={claims.rol === "ADMINISTRADOR"} />
    </>
  );
}
