/**
 * PAN-CFG-NOT — Configuración · Plantillas (HU-E11-02).
 *
 * El listado se pide siempre: el backend siembra las plantillas de fábrica que falten la
 * primera vez que una empresa entra acá.
 *
 * El encabezado lo dibuja el componente, igual que en respuestas frecuentes: las dos pantallas
 * de configuración del canal comparten la misma cabecera, y tenerla en un solo lado es lo que
 * evita que se separen con el tiempo.
 */

import { redirect } from "next/navigation";

import { AdvertenciaDeRecordatorio, PlantillasDeNotificacion } from "@/features/conversational";
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
      <AdvertenciaDeRecordatorio plantillas={listado.plantillas} />
      <PlantillasDeNotificacion inicial={listado} puedeEditar={claims.rol === "ADMINISTRADOR"} />
    </>
  );
}
