/**
 * The authenticated admin panel.
 *
 * The session check lives here, at the group boundary, so that no screen inside can
 * forget it. It does two things now, where it used to do one:
 *
 * 1. **There is a session.** No cookie, no panel.
 * 2. **No legal document is pending** (HU-E1-03 RN-03, HU-E1-08 RN-05). When a version in force
 *    changes, the API answers 403 to everything but a short list; the panel sends the person to
 *    `/aceptacion-legal` **before** looking at the onboarding. Without this the 403 would fall
 *    into `estadoDeEmpresa`, which treats every 4xx as an invalid session, and bounce them to
 *    the login in a loop. A person already inside when it happens is sent there by
 *    `VigilanteDeAceptacionLegal`, which watches the calls the screens make.
 * 3. **The onboarding is finished.** HU-E1-01 RN-04 keeps the dashboard closed until the
 *    company has its fiscal data, and doing it here means every screen added later is
 *    covered without anybody remembering to.
 *
 * The checks after the first cost one API call per navigation. Carrying the flag in the JWT would
 * save it and be wrong: the token lives fifteen minutes, so somebody who just finished
 * step 2 would keep being bounced back to it.
 *
 * **La navegación es una barra lateral, y eso es un arreglo y no una preferencia.** Antes era
 * una fila de enlaces arriba: con veinte pantallas esa fila se partía en tres líneas y cortaba
 * los nombres al medio — que es exactamente lo que muestra la captura de PRU-09. El prototipo
 * (`docs/aidlc/inputs/prototipos/styles.css`) los pone en una columna fija de 244 px agrupados
 * por para qué sirven, y una columna crece hacia abajo sin empujar nada.
 *
 * **Los grupos son el mapa, no decoración.** «Operaciones» es el día a día, «Análisis» es lo
 * que se lee después, «Sistema» es lo que se configura una vez. Quien busca dónde invitar a un
 * usuario no tiene que leer veinte etiquetas, sólo tres grupos.
 *
 * The navigation lists what exists. Entries are added by the unit that builds the screen
 * behind them, never in advance: a menu item leading nowhere is a bug report waiting to
 * be filed.
 */

import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { BotonDeSalida, RenovadorDeSesion, VigilanteDeAceptacionLegal } from "@/features/identity";
import type { DocumentoLegal } from "@/features/identity";
import { ErrorDeApi, llamarApi } from "@/lib/api";
import { haySesion, leerClaims } from "@/lib/session";

import { CarcasaDelPanel } from "./carcasa-del-panel";

interface EstadoDeEmpresa {
  readonly razon_social: string | null;
  readonly onboarding_completo: boolean;
  /** Absent when the panel is deployed before the API that sends it: read as "none". */
  readonly aceptaciones_pendientes?: readonly DocumentoLegal[];
}

export default async function PanelLayout({
  children,
}: {
  readonly children: ReactNode;
}): Promise<JSX.Element> {
  if (!haySesion()) {
    // The access cookie lasts fifteen minutes; the refresh cookie, thirty days. Renewing
    // here is what keeps somebody who comes back after a pause from landing on the login.
    redirect("/api/auth/renovar");
  }

  const empresa = await estadoDeEmpresa();
  if (empresa === null) {
    // The cookie exists but the API rejected it: expired or revoked. Back to the door.
    redirect("/");
  }
  if ((empresa.aceptaciones_pendientes ?? []).length > 0) {
    redirect("/aceptacion-legal");
  }
  if (!empresa.onboarding_completo) {
    redirect("/onboarding/empresa");
  }

  const claims = leerClaims();
  const nombre = empresa.razon_social ?? "Tu empresa";

  return (
    <>
      <VigilanteDeAceptacionLegal />
      <CarcasaDelPanel
        nombre={nombre}
        rol={claims?.rol ?? ""}
        renovador={<RenovadorDeSesion />}
        salida={<BotonDeSalida />}
      >
        {children}
      </CarcasaDelPanel>
    </>
  );
}

async function estadoDeEmpresa(): Promise<EstadoDeEmpresa | null> {
  try {
    return await llamarApi<EstadoDeEmpresa>("/auth/empresa");
  } catch (error) {
    if (error instanceof ErrorDeApi && error.status < 500) {
      return null;
    }
    throw error;
  }
}
