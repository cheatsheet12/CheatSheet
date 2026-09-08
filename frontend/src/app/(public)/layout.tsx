/**
 * Todo lo que se alcanza sin sesión: el ingreso (PAN-ONB-01), el paso 2 del onboarding
 * (PAN-ONB-02), la aceptación de una invitación y el acceso del contador.
 *
 * **Estas pantallas no tienen el shell del panel, y por eso tienen maqueta propia.** Sin
 * sesión no hay barra lateral ni topbar, porque no hay a dónde navegar: quien llega está
 * creando una cuenta o siguiendo un enlace. Lo que queda es lo primero que alguien ve del
 * producto, así que lleva la marca arriba, una columna centrada y un fondo propio — no un
 * formulario suelto sobre blanco.
 *
 * El contenedor es un `<div>` y no un `<main>` a propósito: la página del contador declara
 * su propio `<main>`, y dos landmarks anidados le dicen a un lector de pantalla que hay dos
 * contenidos principales.
 */

import type { ReactNode } from "react";

export default function PublicLayout({ children }: { readonly children: ReactNode }): JSX.Element {
  return (
    <div className="acc-pantalla">
      {/* El imagotipo de `docs/aidlc/inputs/prototipos/imagotipo.html`: símbolo, «Cheat» en
          primario y «Sheet» en acento. */}
      <div className="acc-marca">
        <span className="acc-marca__simbolo" aria-hidden="true">
          CS
        </span>
        <span className="acc-marca__texto">
          <span className="acc-marca__nombre">
            Cheat<em>Sheet</em>
          </span>
          <span className="acc-marca__bajada">Automatización PyME</span>
        </span>
      </div>

      <div className="acc-contenido">{children}</div>

      <p className="acc-nota">
        CheatSheet · Plataforma de gestión para pequeñas y medianas empresas
      </p>
    </div>
  );
}
