/**
 * The button.
 *
 * `variante="peligro"` is for actions that cannot be undone — voiding a document,
 * refunding a payment. Keeping that distinction in the design system rather than in
 * each screen is what stops it from being decided per-feature by whoever was in a
 * hurry.
 */

import type { ButtonHTMLAttributes, ReactNode } from "react";

export type VarianteDeBoton = "primario" | "secundario" | "peligro";

export interface PropsDeBoton extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "className"> {
  readonly variante?: VarianteDeBoton;
  readonly children: ReactNode;
}

const ESTILO_BASE = {
  borderRadius: "var(--radio)",
  border: "var(--borde)",
  padding: "var(--espacio-2) var(--espacio-4)",
  fontSize: "var(--tipo-base)",
  fontFamily: "inherit",
  cursor: "pointer",
} as const;

const POR_VARIANTE: Record<VarianteDeBoton, Record<string, string>> = {
  primario: {
    background: "var(--color-primario)",
    color: "var(--color-primario-contraste)",
    borderColor: "transparent",
  },
  secundario: {
    background: "transparent",
    color: "var(--color-texto)",
  },
  peligro: {
    background: "var(--color-peligro)",
    color: "#ffffff",
    borderColor: "transparent",
  },
};

export function Button({
  variante = "primario",
  children,
  type = "button",
  ...resto
}: PropsDeBoton): JSX.Element {
  return (
    <button type={type} style={{ ...ESTILO_BASE, ...POR_VARIANTE[variante] }} {...resto}>
      {children}
    </button>
  );
}
