/**
 * Inline message.
 *
 * `tono="error"` renders with `role="alert"`, so a screen reader announces it without
 * the user having to go looking. A validation failure the user cannot perceive is a
 * validation failure that did not happen.
 */

import type { ReactNode } from "react";

export type TonoDeAlerta = "info" | "exito" | "atencion" | "error";

export interface PropsDeAlerta {
  readonly tono?: TonoDeAlerta;
  readonly titulo?: string;
  readonly children: ReactNode;
}

const COLOR: Record<TonoDeAlerta, string> = {
  info: "var(--color-primario)",
  exito: "var(--color-exito)",
  atencion: "var(--color-atencion)",
  error: "var(--color-peligro)",
};

export function Alert({ tono = "info", titulo, children }: PropsDeAlerta): JSX.Element {
  return (
    <div
      role={tono === "error" ? "alert" : "status"}
      style={{
        borderLeft: `3px solid ${COLOR[tono]}`,
        background: "var(--color-superficie)",
        borderRadius: "var(--radio)",
        padding: "var(--espacio-3) var(--espacio-4)",
        color: "var(--color-texto)",
      }}
    >
      {titulo !== undefined && (
        <strong style={{ display: "block", color: COLOR[tono] }}>{titulo}</strong>
      )}
      {children}
    </div>
  );
}
