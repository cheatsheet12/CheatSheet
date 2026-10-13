/**
 * El alta de una cuenta: el paso 2 del onboarding (PAN-ONB-02) y la aceptación de una
 * invitación. Quien llega tiene sesión (o está por tenerla) pero todavía no tiene panel.
 *
 * Reutiliza la maqueta de dos columnas del ingreso (`lgn-*`) para que el primer contacto con
 * el producto sea una sola pieza: a la izquierda, dónde está la persona dentro del alta y
 * para qué se le pide lo que se le pide; a la derecha, el formulario. Lo propio de este
 * grupo —el stepper vertical— vive en `pantalla-alta.css` con prefijo `alta-`.
 *
 * Vive en su propio grupo de rutas porque el acceso del contador, que sigue en `(public)`,
 * es un documento ancho y no querría un panel de marca al lado. La URL no cambia.
 */

import Image from "next/image";
import type { ReactNode } from "react";

import { VigilanteDeAceptacionLegal } from "@/features/identity";

import { PanelDelAlta } from "./_componentes/PanelDelAlta";

export default function LayoutDelAlta({ children }: { readonly children: ReactNode }): JSX.Element {
  return (
    <div className="lgn alta">
      <VigilanteDeAceptacionLegal />
      <aside className="lgn-marca alta-panel" aria-label="Tu alta en CheatSheet">
        <div className="lgn-fondo" aria-hidden="true" />

        <div className="lgn-marca__logo">
          <Image src="/logo-simbolo.png" alt="" width={44} height={44} priority />
          <span className="lgn-marca__nombre">
            Cheat<em>Sheet</em>
          </span>
        </div>

        <PanelDelAlta />

        <p className="lgn-marca__pie">Plataforma de gestión para pequeñas y medianas empresas</p>
      </aside>

      <main className="lgn-form">
        <div className="lgn-form__marca-movil">
          <Image src="/logo-simbolo.png" alt="" width={36} height={36} priority />
          <span className="lgn-form__nombre">
            Cheat<em>Sheet</em>
          </span>
        </div>
        <div className="lgn-form__contenido">{children}</div>
      </main>
    </div>
  );
}
