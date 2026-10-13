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
 *
 * **It is also where MercadoPago's OAuth2 redirect lands** (decision D-a of
 * `conexion-mercadopago`): `redirect_uri` points here, so the `?code&state` the provider
 * appends arrives as `searchParams`. Reading it on the server and handing it to the grid
 * keeps the exchange on the one path that has the session cookie — and adds no route that
 * exists only to bounce.
 */

import { redirect } from "next/navigation";

import { GrillaDeIntegraciones } from "@/features/integrations";
import type { ListadoDeIntegraciones, RetornoDeAutorizacion } from "@/features/integrations";
import { llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Integraciones · CheatSheet" };

/** OAuth2 query parameters, as the provider appends them. */
interface ParametrosDeRetorno {
  readonly code?: string;
  readonly state?: string;
  readonly error?: string;
}

/**
 * Reads the return leg out of the query string, or `null` on an ordinary visit.
 *
 * The system is not in the URL because a `redirect_uri` is registered once, whole, at the
 * provider — and MercadoPago is the only system connected this way. When a second one
 * appears it brings its own registered URI, and this becomes a lookup.
 */
function retornoDe(parametros: ParametrosDeRetorno): RetornoDeAutorizacion | null {
  const { code, state, error } = parametros;
  if (code === undefined && error === undefined) {
    return null;
  }
  return {
    sistema: "MERCADOPAGO",
    codigo: code ?? null,
    estado: state ?? null,
    error: error ?? null,
  };
}

export default async function PaginaDeIntegraciones({
  searchParams,
}: {
  searchParams: ParametrosDeRetorno;
}): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  const listado = await llamarApi<ListadoDeIntegraciones>("/integraciones");

  return (
    <>
      <header className="dm-encabezado">
        <div>
          <span className="dm-encabezado__cintillo">Configuración · Paso 3 del onboarding</span>
          <h1>Integraciones</h1>
          <p className="dm-intro">
            Conectá las herramientas que ya usás. El estado se verifica contra cada servicio.
          </p>
        </div>
      </header>
      <GrillaDeIntegraciones
        inicial={listado}
        puedeConectar={claims.rol === "ADMINISTRADOR"}
        retorno={retornoDe(searchParams)}
        cuitDeCheatsheet={process.env.CUIT_DE_CHEATSHEET ?? null}
      />
    </>
  );
}
