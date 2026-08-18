/**
 * Root layout: the only place the design system is loaded, and the only `<html>`.
 *
 * **The fonts are self-hosted, not fetched from Google at runtime.** `next/font/google`
 * downloads them at build time and serves them from our own origin. That removes a
 * third-party request from every page load — one less round trip, and no visitor's IP
 * handed to Google just for a typeface. It does mean the build needs network access to
 * fetch them once; CI does not run `next build`, so only a deploy is affected.
 *
 * `display: swap` shows the fallback immediately and swaps when the font arrives,
 * instead of leaving the panel blank while it downloads.
 */

import { DM_Sans, JetBrains_Mono } from "next/font/google";
import type { Metadata } from "next";
import type { ReactNode } from "react";

import "@/shared/tokens.css";
import "@/shared/componentes.css";

// §1.2: DM Sans for the panel, JetBrains Mono for CUIT, CAE and document numbers.
const dmSans = DM_Sans({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-dm-sans",
  weight: ["400", "600", "700"],
});

const jetBrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-jetbrains-mono",
  weight: ["400"],
});

export const metadata: Metadata = {
  title: "CheatSheet",
  description: "Plataforma de gestión para pequeñas y medianas empresas",
};

export default function RootLayout({ children }: { readonly children: ReactNode }): JSX.Element {
  return (
    <html lang="es" className={`${dmSans.variable} ${jetBrainsMono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
