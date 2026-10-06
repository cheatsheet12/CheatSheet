/**
 * Status pill — specification §1.3, "Badge de estado".
 *
 * 11.5 px is below the 12 px floor the specification sets for visible text, and it is
 * allowed here for one reason: the stylesheet always draws a coloured dot alongside the
 * word, so the meaning does not rest on reading it.
 *
 * The dot is a `::before`, not an element. It is decoration — the word already says the
 * state — and a screen reader announcing a bullet before every status would only make the
 * table longer to listen to.
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
