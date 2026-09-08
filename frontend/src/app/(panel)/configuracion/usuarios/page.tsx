/**
 * PAN-USR-01 — the company's users.
 *
 * A server component that fetches and a client component that interacts. The list is
 * read here, with the session cookie, so the first paint already has the data instead of
 * a spinner that resolves into the same thing.
 */

import { redirect } from "next/navigation";

import { TablaDeUsuarios } from "@/features/identity";
import type { RolUsuario, UsuarioDeLaEmpresa } from "@/features/identity";
import { llamarApi } from "@/lib/api";
import { leerClaims } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = { title: "Usuarios · CheatSheet" };

export default async function PaginaDeUsuarios(): Promise<JSX.Element> {
  const claims = leerClaims();
  if (claims === null) {
    redirect("/");
  }

  const usuarios = await llamarApi<readonly UsuarioDeLaEmpresa[]>("/usuarios");

  return (
    <>
      <header className="dm-encabezado">
        <div>
          <span className="dm-encabezado__cintillo">Configuración</span>
          <h1>Usuarios</h1>
          <p className="dm-intro">
            Quién entra a la empresa y con qué rol. Una invitación queda pendiente hasta que la
            persona elige su contraseña.
          </p>
        </div>
      </header>
      <TablaDeUsuarios
        usuarios={usuarios}
        rolDelUsuarioActual={claims.rol as RolUsuario}
        usuarioActualId={claims.usuarioId}
      />
    </>
  );
}
