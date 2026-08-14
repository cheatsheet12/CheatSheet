/**
 * Action buttons — specification §1.3, "Elementos de Acción".
 *
 * `variante="destructivo"` is for what cannot be undone: voiding a document, refunding
 * a payment, revoking an accountant's access. The specification requires those to ask
 * before running, so `onConfirmar` is part of the component rather than something each
 * screen remembers to add — the one that forgets is the one that deletes.
 */

"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";

export type VarianteDeBoton = "primario" | "secundario" | "destructivo";

export interface PropsDeBoton
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "className" | "onClick"> {
  readonly variante?: VarianteDeBoton;
  readonly cargando?: boolean;
  /** Shown in a `confirm` before running. Only meaningful on `destructivo`. */
  readonly confirmacion?: string;
  readonly onClick?: () => void;
  readonly children: ReactNode;
}

export function Button({
  variante = "primario",
  cargando = false,
  confirmacion,
  onClick,
  children,
  type = "button",
  disabled,
  ...resto
}: PropsDeBoton): JSX.Element {
  const manejarClick = (): void => {
    if (onClick === undefined) {
      return;
    }
    if (confirmacion !== undefined && !window.confirm(confirmacion)) {
      return;
    }
    onClick();
  };

  return (
    <button
      type={type}
      className={`boton boton--${variante}`}
      // Loading is also disabled: the specification replaces the label with a spinner,
      // and a button that still accepts clicks while working submits twice.
      disabled={disabled === true || cargando}
      aria-busy={cargando}
      onClick={manejarClick}
      {...resto}
    >
      {cargando ? <span className="boton__spinner" aria-hidden="true" /> : null}
      {children}
    </button>
  );
}
