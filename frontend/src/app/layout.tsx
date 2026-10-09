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
import "@/shared/controles-de-fecha.css";
// Las cuatro pantallas de auditoría, notificaciones y soporte traen su propia hoja: lo que
// sólo usa un puñado de pantallas no engorda el catálogo compartido.
import "@/shared/pantallas-auditoria.css";
import "@/shared/pantallas-agente.css";
import "@/shared/pantalla-plantillas.css";
// Después del catálogo compartido: las pantallas de Cobros y Facturación ajustan piezas
// propias sobre él, y un import antes las dejaría perdiendo la cascada por orden de carga.
import "@/shared/pantallas-cobros.css";
import "@/shared/pantalla-reglas.css";
import "@/shared/pantalla-puntos-de-venta.css";
import "@/shared/pantallas-identidad.css";
import "@/shared/pantalla-de-ingreso.css";
import "@/shared/pantalla-alta.css";
import "@/shared/pantalla-integraciones.css";
import "@/shared/pantallas-ingesta.css";
// Reportería va después de `componentes.css` a propósito: ahí sobrevive un `.rep-…` viejo del
// catálogo compartido (la barra horizontal, el filtro, la previsualización) que estas tres
// pantallas rehacen, y cargada antes las perdería por orden de carga y no por especificidad.
import "@/shared/pantallas-reportes.css";
import "@/shared/pantalla-paquete-contable.css";
// Datos Maestros va última de las hojas de pantalla: sus reglas `.mae-panel .tabla…` ajustan
// la tabla del catálogo compartido, y cargarla antes de `pantallas-identidad.css` la dejaría
// perdiendo la cascada contra `.dm-` por orden de carga y no por especificidad.
import "@/shared/pantallas-maestros.css";
// Va última: unifica el hover de las tarjetas por encima de las reglas de cada pantalla.
import "@/shared/tarjetas.css";

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
