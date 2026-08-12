/**
 * The authenticated admin panel.
 *
 * The session check lives here, at the group boundary, so that no screen inside can
 * forget it. Today it only checks that the cookie exists; validating the JWT is the
 * next unit (`identidad-y-onboarding`), and this is where that check goes — one place,
 * not one per page.
 *
 * The navigation lists what exists. Entries are added by the unit that builds the
 * screen behind them, never in advance: a menu item leading nowhere is a bug report
 * waiting to be filed.
 */

import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { haySesion } from "@/lib/session";

export default function PanelLayout({ children }: { readonly children: ReactNode }): JSX.Element {
  if (!haySesion()) {
    redirect("/");
  }

  return (
    <div style={{ display: "grid", gridTemplateRows: "auto 1fr", minHeight: "100dvh" }}>
      <header
        style={{
          borderBottom: "var(--borde)",
          padding: "var(--espacio-3) var(--espacio-6)",
          display: "flex",
          alignItems: "center",
          gap: "var(--espacio-4)",
        }}
      >
        <strong>CheatSheet</strong>
        <nav aria-label="Secciones" style={{ color: "var(--color-texto-suave)" }}>
          <span style={{ fontSize: "var(--tipo-chico)" }}>
            Las secciones se agregan con la unidad que construye cada pantalla
          </span>
        </nav>
      </header>
      <main style={{ padding: "var(--espacio-6)" }}>{children}</main>
    </div>
  );
}
