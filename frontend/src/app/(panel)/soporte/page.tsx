/**
 * PAN-SOP-01 — Soporte · Nueva solicitud (HU-E9-03).
 *
 * **Sólo el Administrador abre** (el actor de la historia). El resto ve el estado de lo que ya
 * está abierto, que es lo que evita que dos personas reporten lo mismo dos veces.
 */

import { redirect } from "next/navigation";

import { Soporte } from "@/features/observability";
import type { ListadoDeSolicitudes } from "@/features/observability";
import { llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Soporte · CheatSheet" };

export default async function PaginaDeSoporte(): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  const listado = await llamarApi<ListadoDeSolicitudes>("/soporte");

  return (
    <>
      <h1>Soporte</h1>
      <p className="dm-intro">
        Contanos qué necesitás y el equipo de CheatSheet te contesta por email.
      </p>
      <Soporte inicial={listado.solicitudes} puedeAbrir={claims.rol === "ADMINISTRADOR"} />
    </>
  );
}
