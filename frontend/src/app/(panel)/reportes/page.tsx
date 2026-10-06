/**
 * PAN-REP-01 — Reportería · Tablero (HU-E10-01, HU-E10-02, HU-E10-03).
 *
 * Un componente de servidor que trae y dos de cliente que filtran, como el resto del panel.
 * El rol decide si aparece el generador: **todos ven el tablero** (RN-04 y RN-05), y sólo
 * Administrador y Operador piden archivos.
 */

import { redirect } from "next/navigation";

import { GeneradorDeReportes, Tablero } from "@/features/reporting";
import type { ListadoDeReportes, TableroRespuesta } from "@/features/reporting";
import { llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Reportes · CheatSheet" };

export default async function PaginaDeReportes(): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  const puedeGenerar = claims.rol === "ADMINISTRADOR" || claims.rol === "OPERADOR";
  const tablero = await llamarApi<TableroRespuesta>("/reporteria/tablero");
  const reportes = puedeGenerar
    ? await llamarApi<ListadoDeReportes>("/reporteria/reportes")
    : { reportes: [] };

  return (
    <>
      <header className="rep-cabecera">
        <div>
          <p className="rep-eyebrow">Análisis · Reportes</p>
          <h1 className="rep-titulo">Reportes</h1>
          <p className="rep-sub">
            Lo que pasó en el período: facturación, cobranzas, agenda y operaciones, con la
            variación contra el período anterior.
          </p>
        </div>
      </header>
      <Tablero inicial={tablero} />
      <GeneradorDeReportes
        inicial={reportes.reportes}
        periodo={{ desde: tablero.desde, hasta: tablero.hasta }}
        puedeGenerar={puedeGenerar}
      />
    </>
  );
}
