/**
 * Select — the same contract as `Campo`, for a closed list of options.
 *
 * A native `<select>`, not a custom listbox: roles, keyboard navigation and the mobile
 * picker come for free, and none of the three screens that need one asks for anything a
 * custom widget would add.
 */

import type { SelectHTMLAttributes } from "react";

export interface OpcionDeSelect {
  readonly valor: string;
  readonly etiqueta: string;
}

export interface PropsDeSelect
  extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "className" | "id" | "children"> {
  readonly id: string;
  readonly etiqueta: string;
  readonly opciones: readonly OpcionDeSelect[];
  readonly error?: string | undefined;
  readonly ayuda?: string | undefined;
}

export function Select({
  id,
  etiqueta,
  opciones,
  error,
  ayuda,
  ...resto
}: PropsDeSelect): JSX.Element {
  const idError = `${id}-error`;
  const idAyuda = `${id}-ayuda`;
  const descrito = [error !== undefined ? idError : null, ayuda !== undefined ? idAyuda : null]
    .filter((valor): valor is string => valor !== null)
    .join(" ");

  return (
    <div className={`campo${error !== undefined ? " campo--con-error" : ""}`}>
      <label className="campo__etiqueta" htmlFor={id}>
        {etiqueta}
      </label>
      <select
        id={id}
        className="campo__control"
        aria-invalid={error !== undefined}
        aria-describedby={descrito === "" ? undefined : descrito}
        {...resto}
      >
        {opciones.map((opcion) => (
          <option key={opcion.valor} value={opcion.valor}>
            {opcion.etiqueta}
          </option>
        ))}
      </select>
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
