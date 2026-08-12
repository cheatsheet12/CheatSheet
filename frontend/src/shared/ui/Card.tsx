/**
 * A bounded surface. The panel is a list of these: one per document, payment or
 * appointment.
 */

import type { ReactNode } from "react";

export interface PropsDeCard {
  readonly titulo?: string;
  readonly children: ReactNode;
}

export function Card({ titulo, children }: PropsDeCard): JSX.Element {
  return (
    <section
      style={{
        background: "var(--color-superficie)",
        border: "var(--borde)",
        borderRadius: "var(--radio)",
        padding: "var(--espacio-6)",
      }}
    >
      {titulo !== undefined && (
        <h2
          style={{
            margin: `0 0 var(--espacio-3)`,
            fontSize: "var(--tipo-titulo)",
            fontWeight: 600,
          }}
        >
          {titulo}
        </h2>
      )}
      {children}
    </section>
  );
}
