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
      <header className="dm-encabezado">
        <div>
          <span className="dm-encabezado__cintillo">Configuración</span>
          <h1>Mis preferencias</h1>
          <p className="dm-intro">
            Cómo querés ver las fechas y los números, y por qué canal querés que te avisemos.
          </p>
        </div>
      </header>
      <FormularioDePreferencias iniciales={actuales} />
    </>
  );
}
