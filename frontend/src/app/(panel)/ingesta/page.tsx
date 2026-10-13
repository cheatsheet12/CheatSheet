/**
 * PAN-ING-01 — Ingesta de Datos · Carga (HU-E2-04, HU-E3-03).
 *
 * A server component that fetches and a client component that interacts, like the three
 * master-data screens. The listing is read here with the session cookie, so the first
 * paint already has rows.
 *
 * The role decides whether the write actions render: HU-E2-04's actor is the
 * Administrador, and HU-E3-05 RN-04 gives Solo Lectura the right to look. Hiding the
 * actions is a courtesy — the backend refuses regardless, which is what PRU-09 taught.
 */

import { redirect } from "next/navigation";

import { IngestaDePlanillas } from "@/features/spreadsheet_sync";
import type { ListadoDeCargas, ListadoDeVinculos } from "@/features/spreadsheet_sync";
import { llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Ingesta de datos · CheatSheet" };

export default async function PaginaDeIngesta({
  searchParams,
}: {
  searchParams?: { error?: string };
} = {}): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  // Las dos lecturas en paralelo: son independientes y la pantalla necesita las dos para
  // su primer render.
  const [listado, cargas] = await Promise.all([
    llamarApi<ListadoDeVinculos>("/planillas"),
    llamarApi<ListadoDeCargas>("/planillas/cargas"),
  ]);

  return (
    <>
      {/* La cabecera del prototipo: la miga de pan en el `eyebrow`, el título grande y el
          subtítulo. La miga se escribe acá y no en el layout porque es la única que dice en qué
          grupo del menú está esta pantalla, y ese dato es de la pantalla. */}
      <div className="ing-encabezado">
        <div>
          <p className="ing-eyebrow">Operaciones · Ingesta de datos</p>
          <h1 className="ing-titulo">Ingesta de datos</h1>
          <p className="ing-subtitulo">
            Traé tus clientes y servicios desde una planilla. Podés subir un archivo o vincular una
            hoja de Google para que se sincronice sola.
          </p>
        </div>
      </div>
      <IngestaDePlanillas
        inicial={listado}
        cargasIniciales={cargas.cargas}
        puedeEditar={claims.rol === "ADMINISTRADOR"}
        errorInicial={searchParams?.error?.slice(0, 300) ?? null}
      />
    </>
  );
}
