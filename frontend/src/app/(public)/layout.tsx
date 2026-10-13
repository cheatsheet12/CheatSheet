/**
 * Lo que se alcanza sin sesión y no tiene maqueta de dos columnas: hoy, el acceso del
 * contador. El ingreso vive en `(ingreso)`; el onboarding y la invitación, en `(alta)`.
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

import Image from "next/image";
import type { ReactNode } from "react";

export default function PublicLayout({ children }: { readonly children: ReactNode }): JSX.Element {
  return (
    <div className="acc-pantalla">
      {/* El imagotipo de `docs/aidlc/inputs/prototipos/imagotipo.html`: símbolo, «Cheat» en
          primario y «Sheet» en acento. */}
      <div className="acc-marca">
        <Image
          className="acc-marca__simbolo"
          src="/logo-simbolo.png"
          alt=""
          width={44}
          height={44}
          priority
        />
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
