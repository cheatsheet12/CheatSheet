/**
 * `/onboarding/empresa` — PAN-ONB-02.
 *
 * It lives under `(public)` and not `(panel)` on purpose: HU-E1-02 RN-04 keeps the
 * dashboard closed until this step is done, so the person filling it in has a session
 * but no panel yet. The `(panel)` layout would redirect them away from the very screen
 * they need to complete.
 *
 * **It checks one thing before showing the form: that no legal document is pending**
 * (HU-E1-03 RN-03, HU-E1-08 RN-05). Somebody who left the onboarding half done before a new
 * version took effect would otherwise fill in the company's data only for the first save to
 * be refused with a 403. They accept first and finish afterwards. The check is best effort:
 * if the API cannot answer, the form is shown as it always was, because the page has never
 * required a reachable API to render.
 */

import { redirect } from "next/navigation";

import { FormularioDeEmpresa } from "@/features/identity";
import type { EmpresaActual } from "@/features/identity";
import { llamarApi } from "@/lib/api";
import { haySesion } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function DatosDeEmpresa(): Promise<JSX.Element> {
  if (haySesion() && (await debeAceptarTextosLegales())) {
    redirect("/aceptacion-legal");
  }
  return <FormularioDeEmpresa />;
}

async function debeAceptarTextosLegales(): Promise<boolean> {
  try {
    const empresa = await llamarApi<EmpresaActual>("/auth/empresa");
    return (empresa.aceptaciones_pendientes ?? []).length > 0;
  } catch {
    return false;
  }
}
