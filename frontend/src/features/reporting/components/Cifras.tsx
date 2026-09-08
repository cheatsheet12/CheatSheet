/**
 * La tarjeta de métrica de PAN-REP-01 y de la página del contador.
 *
 * Una sola pieza para las dos pantallas: el contador externo ve exactamente los mismos
 * indicadores que el dueño de la empresa, y dos maquetas parecidas terminan divergiendo
 * en el momento menos oportuno.
 *
 * **Un guion no es un cero.** Cuando el período anterior fue cero no hay con qué comparar
 * y la variación llega en `null`: mostrar «0%» le diría a alguien que su negocio no creció
 * cuando la verdad es que el mes pasado no existía.
 *
 * **El valor llega ya formateado.** Formatearlo acá adentro obligaría a la tarjeta a saber
 * si lo que recibe es plata o una cantidad de turnos, y esa decisión es de la pantalla.
 */

import type { ReactNode } from "react";

export type TonoDeCifra = "menta" | "ambar" | "tinta";

export interface PropsDeCifra {
  readonly titulo: string;
  /** Ya formateado y con su signo de pesos si corresponde. Ver el docstring. */
  readonly valor: string;
  readonly pie?: string;
  readonly icono: ReactNode;
  readonly tono: TonoDeCifra;
  /** El porcentaje que mandó el backend, o `null` cuando no hay con qué comparar. */
  readonly variacion?: string | null;
}

function Variacion({ variacion }: { readonly variacion: string | null }): JSX.Element {
  if (variacion === null) {
    return (
      <span className="rep-variacion" title="No hay período anterior con el que comparar">
        —
      </span>
    );
  }
  // Es un porcentaje, no un importe: acá `Number` sólo decide qué flecha se dibuja.
  const sube = Number(variacion) >= 0;
  return (
    <span className={`rep-variacion rep-variacion--${sube ? "sube" : "baja"}`}>
      {sube ? "▲" : "▼"} {variacion}%
    </span>
  );
}

export function Cifra({ titulo, valor, pie, icono, tono, variacion }: PropsDeCifra): JSX.Element {
  return (
    <section className="rep-kpi">
      <div className="rep-kpi__top">
        <span className={`rep-kpi__icono rep-kpi__icono--${tono}`}>{icono}</span>
        <h2 className="rep-kpi__titulo">{titulo}</h2>
        {variacion !== undefined && <Variacion variacion={variacion} />}
      </div>
      <p className="rep-kpi__valor">{valor}</p>
      {pie !== undefined && <p className="rep-kpi__pie">{pie}</p>}
    </section>
  );
}
