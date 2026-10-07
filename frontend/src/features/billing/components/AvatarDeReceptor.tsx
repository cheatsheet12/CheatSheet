/**
 * El avatar con iniciales del receptor de un comprobante.
 *
 * Es el mismo criterio que el de Clientes —primera letra de las dos primeras palabras, un tono
 * estable por nombre— pero local: el avatar de Clientes vive dentro de `master_data` y una
 * feature no importa los internos de otra (R5). El nombre se muestra como viene del dato.
 */

import type { CSSProperties } from "react";

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

/** Un tono estable por nombre, sólo por el rango azul–violeta: el verde y el rojo significan algo. */
export function tonoDe(nombre: string): number {
  let suma = 0;
  for (const caracter of nombre) {
    suma = (suma * 31 + caracter.charCodeAt(0)) % 997;
  }
  return 205 + (suma % 6) * 20;
}

export function AvatarDeReceptor({
  nombre,
  grande = false,
}: {
  readonly nombre: string;
  readonly grande?: boolean;
}): JSX.Element {
  return (
    <span
      className={`fac-avatar${grande ? " fac-avatar--grande" : ""}`}
      aria-hidden="true"
      style={{ "--fac-tono": tonoDe(nombre) } as CSSProperties}
    >
      {inicialesDe(nombre)}
    </span>
  );
}
