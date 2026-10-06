/**
 * Elevated surface — specification §1.3, "Elementos de Contenido".
 *
 * The panel is a list of these: one per document, payment or appointment.
 */

import type { ReactNode } from "react";

export interface PropsDeCard {
  readonly titulo?: string;
  readonly children: ReactNode;
}

export function Card({ titulo, children }: PropsDeCard): JSX.Element {
  return (
    <section className="tarjeta">
      {titulo !== undefined && <h2 className="tarjeta__titulo">{titulo}</h2>}
      {children}
    </section>
  );
}
