/**
 * Form field — specification §1.4: "Etiquetas visibles en todos los campos de
 * formulario".
 *
 * The label is a real `<label>` tied by `htmlFor`, never a placeholder. A placeholder
 * disappears the moment someone starts typing, which is exactly when they need to check
 * what the field was for.
 *
 * When there is an error the field points at it with `aria-describedby` and marks itself
 * `aria-invalid`, so the message reaches a screen reader instead of only being red.
 */

import type { InputHTMLAttributes, ReactNode } from "react";

export interface PropsDeCampo
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "className" | "id"> {
  readonly id: string;
  readonly etiqueta: string;
  // `| undefined` because tsconfig sets exactOptionalPropertyTypes: a caller passing an
  // explicitly undefined error is saying "no error", which is the common case here.
  readonly error?: string | undefined;
  readonly ayuda?: string | undefined;
  /** Monospace, for CUIT, CAE and document numbers (§1.2). */
  readonly mono?: boolean;
}

export function Campo({
  id,
  etiqueta,
  error,
  ayuda,
  mono = false,
  ...resto
}: PropsDeCampo): JSX.Element {
  const idError = `${id}-error`;
  const idAyuda = `${id}-ayuda`;
  const descrito = [error !== undefined ? idError : null, ayuda !== undefined ? idAyuda : null]
    .filter((valor): valor is string => valor !== null)
    .join(" ");

  return (
    <div
      className={`campo${error !== undefined ? " campo--con-error" : ""}${mono ? " campo--mono" : ""}`}
    >
      <label className="campo__etiqueta" htmlFor={id}>
        {etiqueta}
      </label>
      <input
        id={id}
        className="campo__control"
        aria-invalid={error !== undefined}
        aria-describedby={descrito === "" ? undefined : descrito}
        {...resto}
      />
      {ayuda !== undefined && (
        <span className="campo__ayuda" id={idAyuda}>
          {ayuda}
        </span>
      )}
      {error !== undefined && (
        <span className="campo__error" id={idError} role="alert">
          {error}
        </span>
      )}
    </div>
  );
}

export interface PropsDeCasilla
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "className" | "id" | "type"> {
  readonly id: string;
  readonly error?: string | undefined;
  readonly children: ReactNode;
}

/** A checkbox whose label may carry a link — the terms and conditions need one. */
export function Casilla({ id, error, children, ...resto }: PropsDeCasilla): JSX.Element {
  const idError = `${id}-error`;
  return (
    <div className={`campo campo--casilla${error !== undefined ? " campo--con-error" : ""}`}>
      <input
        id={id}
        type="checkbox"
        aria-invalid={error !== undefined}
        aria-describedby={error !== undefined ? idError : undefined}
        {...resto}
      />
      <label htmlFor={id}>{children}</label>
      {error !== undefined && (
        <span className="campo__error" id={idError} role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
