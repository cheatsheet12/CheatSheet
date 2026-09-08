/**
 * PAN-CFG-NOT — Configuración · Notificaciones (HU-E11-03).
 *
 * **Todos los roles entran, y cada uno ve la suya.** El destinatario sale de la sesión del
 * lado del backend, así que esta página no tiene forma de pedir la bandeja de otra persona.
 */

import { redirect } from "next/navigation";

import { CentroDeNotificaciones } from "@/features/observability";
import type { ListadoDeNotificaciones } from "@/features/observability";
import { llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Notificaciones · CheatSheet" };

export default async function PaginaDeNotificaciones(): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  const listado = await llamarApi<ListadoDeNotificaciones>("/notificaciones");

  return (
    <>
      <h1>Notificaciones</h1>
      <p className="dm-intro">
        Lo que necesita tu atención. Qué recibís lo elegís vos en tus preferencias.
      </p>
      <CentroDeNotificaciones inicial={listado} />
    </>
  );
}
