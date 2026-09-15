/**
 * PAN-ING-02 — Ingesta · Revisión del mapeo (HU-E3-01, HU-E3-02).
 *
 * El paso que faltaba entre PAN-ING-01 y el procesamiento. La pantalla ya existía como
 * componente; lo que no existía era una ruta que la montara, así que «Falta mapear» era un
 * callejón sin salida.
 *
 * **Las dos llamadas se hacen acá, en el servidor, y no en el componente.** La pantalla
 * llega con el mapeo ya propuesto en vez de montar un esqueleto y pedirlo después, que es
 * lo que hace el resto del panel.
 *
 * **Proponer dos veces es seguro.** `ProponerMapeo` busca primero por huella de encabezado
 * (RN-02): si ya hay un mapeo para esta estructura lo devuelve sin llamar al modelo. Por
 * eso un `POST` en el render no es un efecto que se duplique al refrescar — es la misma
 * respuesta, y el modelo se consulta una sola vez por estructura.
 */

import { redirect } from "next/navigation";

import { RevisionDeMapeo } from "@/features/spreadsheet_sync";
import type { Mapeo } from "@/features/spreadsheet_sync";
import { llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Revisar mapeo · CheatSheet" };

interface Encabezados {
  readonly columnas: readonly { readonly nombre: string; readonly ejemplo: string | null }[];
}

export default async function PaginaDeMapeo({
  params,
}: {
  params: { vinculoId: string };
}): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  const { columnas } = await llamarApi<Encabezados>(`/planillas/${params.vinculoId}/encabezados`);
  const mapeo = await llamarApi<Mapeo>("/planillas/mapeos", {
    method: "POST",
    body: {
      vinculo_id: params.vinculoId,
      // El ejemplo viaja al panel y nunca al modelo (decisión D12). Se manda como
      // `undefined` y no como `null` cuando la columna está vacía, porque el DTO del
      // backend lo declara opcional.
      columnas: columnas.map(({ nombre, ejemplo }) => ({
        nombre,
        ...(ejemplo !== null ? { ejemplo } : {}),
      })),
    },
  });

  return (
    <>
      <div className="ing-encabezado">
        <div>
          <p className="ing-eyebrow">Operaciones · Ingesta de datos · Mapeo</p>
          <h1 className="ing-titulo">Revisar el mapeo</h1>
          <p className="ing-subtitulo">
            Cada columna de tu planilla, a qué campo va y con cuánta confianza. Corregí lo que haga
            falta: nada se procesa hasta que confirmes.
          </p>
        </div>
      </div>
      <RevisionDeMapeo
        inicial={mapeo}
        vinculoId={params.vinculoId}
        puedeEditar={claims.rol !== "SOLO_LECTURA"}
      />
    </>
  );
}
