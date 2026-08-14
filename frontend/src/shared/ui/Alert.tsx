/**
 * Information box — specification §1.3, "Caja de información".
 *
 * A 4 px left border coloured by kind. Used for business rules, access notes and
 * context messages.
 *
 * `tono="error"` renders with `role="alert"`, so a screen reader announces it without
 * the user going to look for it. A validation failure nobody perceives is a validation
 * failure that did not happen.
 */

import type { ReactNode } from "react";

export type TonoDeAlerta = "neutral" | "exito" | "advertencia" | "error";

export interface PropsDeAlerta {
  readonly tono?: TonoDeAlerta;
  readonly titulo?: string;
  readonly children: ReactNode;
}

const CLASE: Record<TonoDeAlerta, string> = {
  neutral: "caja",
  exito: "caja caja--exito",
  advertencia: "caja caja--advertencia",
  error: "caja caja--error",
};

export function Alert({ tono = "neutral", titulo, children }: PropsDeAlerta): JSX.Element {
  return (
    <div className={CLASE[tono]} role={tono === "error" ? "alert" : "status"}>
      {titulo !== undefined && <strong className="caja__titulo">{titulo}</strong>}
      {children}
    </div>
  );
}
