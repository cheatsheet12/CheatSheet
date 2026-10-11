/**
 * `/privacidad` — PAN-LEG-01. **Public, with a stable route** (HU-E1-08 RN-06).
 *
 * Same contract as `/terminos`: server-rendered, revalidated hourly, and a failed fetch
 * propagates so Next keeps serving the last good copy instead of caching an error.
 */

import { DocumentoLegalPublico } from "@/features/identity";
import type { DocumentoLegalPublicado } from "@/features/identity";
import { llamarApi } from "@/lib/api";

export const metadata = { title: "Política de Privacidad · CheatSheet" };

export default async function PaginaDePrivacidad(): Promise<JSX.Element> {
  const documento = await llamarApi<DocumentoLegalPublicado>("/legal/privacidad", {
    revalidarCadaSegundos: 3600,
  });

  return (
    <main>
      <DocumentoLegalPublico documento={documento} />
    </main>
  );
}
