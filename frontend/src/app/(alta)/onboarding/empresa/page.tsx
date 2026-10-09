/**
 * `/onboarding/empresa` — PAN-ONB-02.
 *
 * It lives under `(public)` and not `(panel)` on purpose: HU-E1-02 RN-04 keeps the
 * dashboard closed until this step is done, so the person filling it in has a session
 * but no panel yet. The `(panel)` layout would redirect them away from the very screen
 * they need to complete.
 */

import { FormularioDeEmpresa } from "@/features/identity";

export default function DatosDeEmpresa(): JSX.Element {
  return <FormularioDeEmpresa />;
}
