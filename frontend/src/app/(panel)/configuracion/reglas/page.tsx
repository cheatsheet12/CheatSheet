/**
 * PAN-CFG-RN — Configuración · Reglas de negocio (HU-E11-01).
 *
 * Todos los roles ven las reglas con su tipo, prioridad y estado, que es lo que pide el primer
 * criterio. Sólo el Administrador edita, y el caso de uso lo refuerza.
 */

import { redirect } from "next/navigation";

import { ReglasDeNegocio } from "@/features/payments";
import type { ListadoDeReglas } from "@/features/payments";
import { llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Reglas de negocio · CheatSheet" };

export default async function PaginaDeReglas(): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  const listado = await llamarApi<ListadoDeReglas>("/reglas");

  return (
    <>
      <header className="dm-encabezado">
        <div>
          <span className="dm-encabezado__cintillo">Configuración</span>
          <h1>Reglas de negocio</h1>
          <p className="dm-intro">
            Sin una cadena configurada rige la de por defecto —a los 3, 7 y 15 días— para que ningún
            cobro se quede sin recordatorios.
          </p>
        </div>
      </header>
      <ReglasDeNegocio inicial={listado} puedeEditar={claims.rol === "ADMINISTRADOR"} />
    </>
  );
}
