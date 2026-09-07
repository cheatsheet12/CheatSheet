/**
 * PAN-REP-02 — Reportería · Configuración automática (HU-E10-04 y HU-E10-05).
 *
 * **Sólo el Administrador configura** (RN-04). El Operador puede llegar a la pantalla y ve el
 * estado, pero los controles vienen deshabilitados y el backend rechaza el `PUT` igual: ocultar
 * un botón es una cortesía, negar el caso de uso es la garantía.
 */

import { redirect } from "next/navigation";

import { ConfiguracionDelPaquete } from "@/features/reporting";
import type { ConfiguracionDelPaqueteRespuesta, ListadoDePaquetes } from "@/features/reporting";
import { llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Paquete contable · CheatSheet" };

export default async function PaginaDelPaqueteContable(): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  const configuracion = await llamarApi<ConfiguracionDelPaqueteRespuesta>(
    "/reporteria/configuracion",
  );
  const paquetes = await llamarApi<ListadoDePaquetes>("/reporteria/paquetes");

  return (
    <>
      <h1>Paquete contable</h1>
      <p className="dm-intro">
        El paquete del mes cerrado sale solo el día que elijas, y tu contador lo descarga con un
        enlace que podés revocar cuando quieras.
      </p>
      <ConfiguracionDelPaquete
        inicial={configuracion}
        paquetes={paquetes.paquetes}
        puedeConfigurar={claims.rol === "ADMINISTRADOR"}
      />
    </>
  );
}
