/**
 * Status pill — specification §1.3, "Badge de estado".
 *
 * 11 px is below the 12 px floor the specification sets for visible text, and it is
 * allowed here for one reason: the badge always carries a colour indicator alongside the
 * word, so the meaning does not rest on reading it.
 */

import type { ReactNode } from "react";

export type EstadoDeBadge = "ok" | "atencion" | "pendiente" | "error";

export interface PropsDeBadge {
  readonly estado: EstadoDeBadge;
  readonly children: ReactNode;
}

export function Badge({ estado, children }: PropsDeBadge): JSX.Element {
  return <span className={`badge badge--${estado}`}>{children}</span>;
}
