/**
 * `/terminos` — PAN-LEG-02. **Public, with a stable route** (HU-E1-03 RN-04, RN-05).
 *
 * Rendered on the server and revalidated hourly instead of `no-store`: the terms must be
 * readable by someone who has not signed up, so a backend that is down when Next
 * revalidates must not turn into an error page — Next keeps serving the last good copy.
 * That is also why a failed fetch is not caught here: swallowing it would cache an error
 * page for an hour.
 */

import { DocumentoLegalPublico } from "@/features/identity";
import type { DocumentoLegalPublicado } from "@/features/identity";
import { llamarApi } from "@/lib/api";

export const metadata = { title: "Términos y Condiciones · CheatSheet" };

export default async function PaginaDeTerminos(): Promise<JSX.Element> {
  const documento = await llamarApi<DocumentoLegalPublicado>("/legal/terminos", {
    revalidarCadaSegundos: 3600,
  });

  return (
    <main>
      <DocumentoLegalPublico documento={documento} />
    </main>
  );
}
