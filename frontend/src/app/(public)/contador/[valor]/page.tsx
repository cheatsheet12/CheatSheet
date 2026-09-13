/**
 * La página del contador externo (HU-E10-06). **Pública: no exige sesión.**
 *
 * Vive bajo `(public)` y no bajo `(panel)` porque el layout del panel exige una cookie y
 * redirige sin ella. Acá la credencial es el valor del enlace, y lo que se muestra es lo único
 * que ese enlace habilita: los indicadores del período y los paquetes para descargar.
 *
 * **Un enlace que no sirve no rompe la página**: el error del backend se atrapa y lo que se
 * dibuja es su frase, que es la que la historia pide palabra por palabra.
 */

import { AccesoContable } from "@/features/reporting";
import type { AccesoDelContador } from "@/features/reporting";
import { ErrorDeApi, llamarApi } from "@/lib/api";

export const dynamic = "force-dynamic";

export const metadata = { title: "Paquete contable · CheatSheet" };

interface Props {
  readonly params: { readonly valor: string };
}

export default async function PaginaDelContador({ params }: Props): Promise<JSX.Element> {
  let acceso: AccesoDelContador | null = null;
  let motivo: string | undefined;

  try {
    acceso = await llamarApi<AccesoDelContador>(`/contador/${encodeURIComponent(params.valor)}`);
  } catch (error) {
    if (!(error instanceof ErrorDeApi) || error.status >= 500) {
      throw error;
    }
    motivo = error.detalle;
  }

  return (
    <main className="publico">
      <h1>Paquete contable</h1>
      <AccesoContable valor={params.valor} acceso={acceso} motivo={motivo} />
    </main>
  );
}
