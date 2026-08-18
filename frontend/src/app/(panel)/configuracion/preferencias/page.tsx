/**
 * PAN-USR-02 — personal preferences (HU-E1-07).
 *
 * Any role reaches this screen: it is the one thing in `identity` that acts on the
 * caller themself.
 */

import { FormularioDePreferencias } from "@/features/identity";
import type { Preferencias } from "@/features/identity";
import { llamarApi } from "@/lib/api";

export const dynamic = "force-dynamic";

export const metadata = { title: "Mis preferencias · CheatSheet" };

export default async function PaginaDePreferencias(): Promise<JSX.Element> {
  const actuales = await llamarApi<Preferencias>("/usuarios/yo/preferencias");

  return (
    <>
      <h1>Mis preferencias</h1>
      <FormularioDePreferencias iniciales={actuales} />
    </>
  );
}
