/**
 * Campo de contraseña con botón para mostrarla u ocultarla.
 *
 * Es un componente propio y no una opción de `Campo` porque necesita estado, y `Campo` es un
 * componente sin hooks que también se renderiza desde el servidor. La estructura y las clases son
 * las mismas, así que se ve y se comporta igual que los demás campos.
 *
 * El botón es `type="button"` para no enviar el formulario, y `aria-pressed` le dice a un lector
 * de pantalla si la contraseña está visible. Al ocultarla de nuevo el valor no se toca.
 */

"use client";

import { Eye, EyeOff } from "lucide-react";
import { useState } from "react";
import type { InputHTMLAttributes } from "react";

export interface PropsDeCampoDeContrasena
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "className" | "id" | "type"> {
  readonly id: string;
  readonly etiqueta: string;
  readonly error?: string | undefined;
  readonly ayuda?: string | undefined;
}

export function CampoDeContrasena({
  id,
  etiqueta,
  error,
  ayuda,
  ...resto
}: PropsDeCampoDeContrasena): JSX.Element {
  const [visible, setVisible] = useState(false);
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
      <div className="campo__contrasena">
        <input
          id={id}
          className="campo__control"
          type={visible ? "text" : "password"}
          aria-invalid={error !== undefined}
          aria-describedby={descrito === "" ? undefined : descrito}
          {...resto}
        />
        <button
          type="button"
          className="campo__ver"
          aria-pressed={visible}
          aria-label={visible ? "Ocultar contraseña" : "Mostrar contraseña"}
          title={visible ? "Ocultar contraseña" : "Mostrar contraseña"}
          onClick={() => setVisible((actual) => !actual)}
        >
          {visible ? (
            <EyeOff size={18} strokeWidth={2} aria-hidden="true" />
          ) : (
            <Eye size={18} strokeWidth={2} aria-hidden="true" />
          )}
        </button>
      </div>
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
