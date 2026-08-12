/**
 * Root layout: the only place the design tokens are loaded, and the only `<html>`.
 *
 * The two route groups below it — `(public)` and `(panel)` — differ in chrome and in
 * whether a session is required, not in styling.
 */

import type { Metadata } from "next";
import type { ReactNode } from "react";

import "@/shared/tokens.css";

export const metadata: Metadata = {
  title: "CheatSheet",
  description: "Plataforma de gestión para pequeñas y medianas empresas",
};

export default function RootLayout({ children }: { readonly children: ReactNode }): JSX.Element {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
