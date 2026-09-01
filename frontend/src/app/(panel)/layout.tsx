/**
 * The authenticated admin panel.
 *
 * The session check lives here, at the group boundary, so that no screen inside can
 * forget it. It does two things now, where it used to do one:
 *
 * 1. **There is a session.** No cookie, no panel.
 * 2. **The onboarding is finished.** HU-E1-01 RN-04 keeps the dashboard closed until the
 *    company has its fiscal data, and doing it here means every screen added later is
 *    covered without anybody remembering to.
 *
 * The second check costs one API call per navigation. Carrying the flag in the JWT would
 * save it and be wrong: the token lives fifteen minutes, so somebody who just finished
 * step 2 would keep being bounced back to it.
 *
 * The navigation lists what exists. Entries are added by the unit that builds the screen
 * behind them, never in advance: a menu item leading nowhere is a bug report waiting to
 * be filed.
 */

import Link from "next/link";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { BotonDeSalida } from "@/features/identity";
import { ErrorDeApi, llamarApi } from "@/lib/api";
import { haySesion } from "@/lib/session";

interface EstadoDeEmpresa {
  readonly razon_social: string | null;
  readonly onboarding_completo: boolean;
}

export default async function PanelLayout({
  children,
}: {
  readonly children: ReactNode;
}): Promise<JSX.Element> {
  if (!haySesion()) {
    redirect("/");
  }

  const empresa = await estadoDeEmpresa();
  if (empresa === null) {
    // The cookie exists but the API rejected it: expired or revoked. Back to the door.
    redirect("/");
  }
  if (!empresa.onboarding_completo) {
    redirect("/onboarding/empresa");
  }

  return (
    <div className="panel">
      <header className="panel__barra">
        <strong className="panel__marca">CheatSheet</strong>
        <span className="panel__empresa">{empresa.razon_social}</span>
        <nav aria-label="Secciones" className="panel__nav">
          <Link href="/panel">Inicio</Link>
          <Link href="/datos-maestros/clientes">Clientes</Link>
          <Link href="/datos-maestros/servicios">Servicios</Link>
          <Link href="/configuracion/empresa">Empresa</Link>
          <Link href="/configuracion/usuarios">Usuarios</Link>
          <Link href="/configuracion/integraciones">Integraciones</Link>
          <Link href="/configuracion/preferencias">Mis preferencias</Link>
          <BotonDeSalida />
        </nav>
      </header>
      <main className="panel__contenido">{children}</main>
    </div>
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
