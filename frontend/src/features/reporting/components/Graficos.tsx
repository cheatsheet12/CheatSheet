/**
 * Los dos gráficos de PAN-REP-01, **hechos con divs**.
 *
 * No hay librería de gráficos en este repositorio y esta unidad no introduce ninguna:
 * cinco columnas con su etiqueta se leen igual que un canvas, pesan cero kilobytes y
 * siguen ahí si el JavaScript no llega. El alto de cada barra es un porcentaje en el
 * atributo `style` y el resto lo hace la hoja de estilos.
 *
 * **La única conversión a número que hay acá es la escala**, que es geometría. Todo importe
 * que se *muestra* sale del string que mandó el backend, formateado con `formatearNumero`:
 * un float en el cuarto decimal es donde vive un centavo.
 *
 * **Una barra vacía no es una barra chiquita.** Una semana sin facturación se dibuja como
 * un zócalo gris: con el alto proporcional a cero se vería igual que una semana de mil
 * pesos, y las dos cosas no son lo mismo.
 */

import type { CSSProperties } from "react";

import { PREFERENCIAS_POR_DEFECTO, formatearNumero } from "@/shared";

/** Cuántas columnas caben cómodas antes de apretar el espaciado. */
const COLUMNAS_HOLGADAS = 10;

interface Escala {
  /** El mayor de la serie. Divide para sacar porcentajes; nunca se muestra. */
  readonly tope: number;
  /** Cuál entrada es la mayor, para rotular el eje con **su** string original. */
  readonly indiceMayor: number;
}

function escalaDe(valores: readonly string[]): Escala {
  let tope = 0;
  let indiceMayor = 0;
  valores.forEach((valor, indice) => {
    const numero = Math.abs(Number(valor));
    if (Number.isFinite(numero) && numero > tope) {
      tope = numero;
      indiceMayor = indice;
    }
  });
  // Una serie toda en cero divide por uno: todas las barras dan cero, que es lo correcto.
  return { tope: tope === 0 ? 1 : tope, indiceMayor };
}

function proporcion(valor: string, tope: number): number {
  const numero = Math.abs(Number(valor));
  return Number.isFinite(numero) ? (numero / tope) * 100 : 0;
}

/** `--rep-orden` escalona el arranque de las barras; el CSS lo multiplica por 25 ms. */
function estiloDeBarra(medida: CSSProperties, orden: number): CSSProperties {
  return { ...medida, "--rep-orden": orden } as CSSProperties;
}

export interface PropsDeBarras {
  readonly datos: Readonly<Record<string, string>>;
  readonly vacio: string;
}

export function BarrasPorSemana({ datos, vacio }: PropsDeBarras): JSX.Element {
  const entradas = Object.entries(datos);
  if (entradas.length === 0) {
    return <p className="rep-vacio">{vacio}</p>;
  }

  const { tope, indiceMayor } = escalaDe(entradas.map(([, valor]) => valor));
  const cima = entradas[indiceMayor]?.[1] ?? "0";
  const densa = entradas.length > COLUMNAS_HOLGADAS;

  return (
    <ul className={densa ? "rep-barras rep-barras--densa" : "rep-barras"}>
      <li className="rep-barras__eje" aria-hidden="true">
        <span>$ {formatearNumero(cima, PREFERENCIAS_POR_DEFECTO, 0)}</span>
        <span>$ 0</span>
      </li>
      {entradas.map(([clave, valor], indice) => {
        const alto = proporcion(valor, tope);
        const clases =
          alto === 0 ? "rep-barras__barra rep-barras__barra--vacia" : "rep-barras__barra";
        return (
          <li key={clave} className="rep-barras__col">
            <span className="rep-barras__monto">$ {formatearNumero(valor)}</span>
            <span className={clases} style={estiloDeBarra({ height: `${alto}%` }, indice)} />
            <span className="rep-barras__x">{clave}</span>
          </li>
        );
      })}
    </ul>
  );
}

export interface PropsDeDistribucion {
  readonly datos: Readonly<Record<string, string>>;
  readonly vacio: string;
  /** Cómo se llama en pantalla cada clave del backend (`FACTURA_B` → «Factura b»). */
  readonly nombrar: (clave: string) => string;
}

export function Distribucion({ datos, vacio, nombrar }: PropsDeDistribucion): JSX.Element {
  const entradas = Object.entries(datos);
  if (entradas.length === 0) {
    return <p className="rep-vacio">{vacio}</p>;
  }

  const { tope } = escalaDe(entradas.map(([, valor]) => valor));

  return (
    <ul className="rep-dist">
      {entradas.map(([clave, valor], indice) => (
        <li key={clave} className="rep-dist__fila">
          <span className="rep-dist__sw" aria-hidden="true" />
          <span>
            <span className="rep-dist__nombre">{nombrar(clave)}</span>
            <span className="rep-dist__pista">
              <span
                className="rep-dist__barra"
                style={estiloDeBarra({ width: `${proporcion(valor, tope)}%` }, indice)}
              />
            </span>
          </span>
          <span className="rep-dist__monto">$ {formatearNumero(valor)}</span>
        </li>
      ))}
    </ul>
  );
}
