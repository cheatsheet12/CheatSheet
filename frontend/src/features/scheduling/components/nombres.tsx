/**
 * Cómo se llama lo que un turno señala, y el avatar con las iniciales del cliente.
 *
 * Un `Turno` viaja con ids; los nombres los resuelve la página del servidor. Cuando uno no
 * llegó se muestra el id, que es feo pero es cierto: una celda vacía haría pensar que el turno
 * está mal cargado.
 */

import type { CSSProperties } from "react";

export interface NombresDeAgenda {
  readonly cliente: (id: string) => string;
  readonly servicio: (id: string) => string;
  readonly recurso: (id: string) => string;
}

/** La primera letra de las dos primeras palabras, o las dos primeras de una sola. */
export function inicialesDe(nombre: string): string {
  const palabras = nombre.trim().split(/\s+/).filter(Boolean);
  if (palabras.length === 0) {
    return "?";
  }
  const [primera = "", segunda] = palabras;
  const letras =
    segunda === undefined ? primera.slice(0, 2) : `${primera[0] ?? ""}${segunda[0] ?? ""}`;
  return letras.toUpperCase();
}

/** Un tono estable por nombre, en el rango azul–violeta: el mismo cliente, el mismo color. */
export function tonoDe(nombre: string): number {
  let suma = 0;
  for (const caracter of nombre) {
    suma = (suma * 31 + caracter.charCodeAt(0)) % 997;
  }
  return 205 + (suma % 6) * 20;
}

export function AvatarDeTurno({ nombre }: { readonly nombre: string }): JSX.Element {
  return (
    <span
      className="age-avatar"
      aria-hidden="true"
      style={{ "--age-tono": tonoDe(nombre) } as CSSProperties}
    >
      {inicialesDe(nombre)}
    </span>
  );
}
