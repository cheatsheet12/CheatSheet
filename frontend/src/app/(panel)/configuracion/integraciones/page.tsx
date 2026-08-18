/**
 * PAN-CFG-INT — Configuración · Integraciones (HU-E2-05).
 *
 * A server component that fetches and a client component that interacts, like PAN-USR-01.
 * The listing is read here with the session cookie, so the first paint already has the
 * four cards instead of a spinner that resolves into the same thing.
 *
 * **This is not the third step of the onboarding.** The Etapa 5 navigation map codes this
 * screen PAN-ONB-03; the stories code it PAN-CFG-INT and give an Operador read access to
 * it. Decision D7 of the units map resolved that toward configuration, and the visual
 * design of the mockup is reused unchanged.
 */

import { redirect } from "next/navigation";

import { GrillaDeIntegraciones } from "@/features/integrations";
import type { ListadoDeIntegraciones } from "@/features/integrations";
import { llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Integraciones · CheatSheet" };

export default async function PaginaDeIntegraciones(): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  const listado = await llamarApi<ListadoDeIntegraciones>("/integraciones");

  return (
    <>
      <h1>Integraciones</h1>
      <p className="int-intro">
        Conectá las herramientas que ya usás. El estado se verifica contra cada servicio.
      </p>
      <GrillaDeIntegraciones inicial={listado} puedeConectar={claims.rol === "ADMINISTRADOR"} />
    </>
  );
}
