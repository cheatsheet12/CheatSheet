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
 * **Una sola categoría no es un gráfico, y dibujarla como si lo fuera es mentir.** Con una
 * única serie, cualquier escala la lleva al 100 % del ancho disponible: una barra llena de
 * punta a punta que se lee como «completado» cuando lo que dice es «es el único dato que
 * hay». En ese caso la pantalla muestra el dato —el número, con su nombre y por qué está
 * solo— y no dibuja ninguna barra.
 *
 * **La distribución se mide contra el total, no contra el mayor.** Escalada contra el mayor,
 * la categoría más grande siempre toca el borde y la pantalla dice «todo» donde los datos
 * dicen «la mitad»; contra el total, el ancho de cada barra *es* la parte que le toca.
 *
 * **Una semana vacía no es una barra chiquita.** Una semana sin facturación se dibuja como
 * un zócalo gris: con el alto proporcional a cero se vería igual que una semana de mil
 * pesos, y las dos cosas no son lo mismo.
 */

import type { CSSProperties } from "react";

import { PREFERENCIAS_POR_DEFECTO, formatearNumero } from "@/shared";

/** Cuántas columnas caben cómodas antes de apretar el espaciado. */
const COLUMNAS_HOLGADAS = 10;

/** Cuántas categorías hacen falta para que una comparación sea una comparación. */
const MINIMO_PARA_COMPARAR = 2;

const CIEN_POR_CIENTO = 100;

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

/**
 * La suma de la serie, **para repartir anchos y nada más**.
 *
 * Es la única suma de importes que ocurre en el navegador, y ninguno de sus dígitos se
 * muestra: de acá sale un porcentaje de ancho y un rótulo redondeado a entero. El total en
 * pesos que la pantalla exhibe siempre es el que calculó el backend (`CLAUDE.md` §5).
 */
function sumaDe(valores: readonly string[]): number {
  const total = valores.reduce((acumulado, valor) => {
    const numero = Math.abs(Number(valor));
    return Number.isFinite(numero) ? acumulado + numero : acumulado;
  }, 0);
  return total === 0 ? 1 : total;
}

function proporcion(valor: string, tope: number): number {
  const numero = Math.abs(Number(valor));
  return Number.isFinite(numero) ? (numero / tope) * CIEN_POR_CIENTO : 0;
}

/** `--rep-orden` escalona el arranque de las barras; el CSS lo multiplica por 25 ms. */
function estiloDeBarra(medida: CSSProperties, orden: number): CSSProperties {
  return { ...medida, "--rep-orden": orden } as CSSProperties;
}

export interface PropsDeSerie {
  readonly datos: Readonly<Record<string, string>>;
  readonly vacio: string;
  /** Cómo se llama en pantalla cada clave del backend (`FACTURA_B` → «Factura B»). */
  readonly nombrar: (clave: string) => string;
  /** La versión larga del nombre, para cuando hay una sola categoría y sobra el lugar. */
  readonly detallar?: (clave: string) => string;
  /** Lo que se dice cuando hay una sola categoría. Depende de qué se esté midiendo. */
  readonly notaUnica: string;
}

export interface PropsDeDistribucion extends PropsDeSerie {
  /** Un rótulo secundario por categoría (la cantidad), junto al nombre. */
  readonly secundario?: (clave: string) => string;
}

/** El signo viaja en el texto del backend: no hace falta convertirlo para saberlo. */
function esNegativo(valor: string): boolean {
  return valor.startsWith("-");
}

/**
 * El dato solo, sin gráfico.
 *
 * Sin una segunda categoría no hay nada que comparar, así que lo honesto es mostrar el número
 * grande y decir en una línea por qué está solo. Es la misma jerarquía que una tarjeta de
 * cifra —rótulo, número, contexto— para que la pantalla no invente un cuarto tipo de caja.
 */
function DatoUnico({
  rotulo,
  monto,
  nota,
}: {
  readonly rotulo: string;
  readonly monto: string;
  readonly nota: string;
}): JSX.Element {
  return (
    <div className="rep-unico">
      <p className="rep-unico__rotulo">{rotulo}</p>
      <p className="rep-unico__cifra">$ {formatearNumero(monto)}</p>
      <p className="rep-unico__nota">{nota}</p>
    </div>
  );
}

export function BarrasPorSemana({
  datos,
  vacio,
  nombrar,
  detallar,
  notaUnica,
}: PropsDeSerie): JSX.Element {
  const entradas = Object.entries(datos);
  const primera = entradas[0];
  if (primera === undefined) {
    return <p className="rep-vacio">{vacio}</p>;
  }
  if (entradas.length < MINIMO_PARA_COMPARAR) {
    return (
      <DatoUnico rotulo={(detallar ?? nombrar)(primera[0])} monto={primera[1]} nota={notaUnica} />
    );
  }

  const { tope, indiceMayor } = escalaDe(entradas.map(([, valor]) => valor));
  // El eje mide magnitud: una semana negativa se dibuja hacia arriba, con otro color.
  const cima = (entradas[indiceMayor]?.[1] ?? "0").replace(/^-/, "");
  const densa = entradas.length > COLUMNAS_HOLGADAS;

  return (
    <ul className={densa ? "rep-barras rep-barras--densa" : "rep-barras"}>
      <li className="rep-barras__eje" aria-hidden="true">
        <span>$ {formatearNumero(cima, PREFERENCIAS_POR_DEFECTO, 0)}</span>
        <span>$ 0</span>
      </li>
      {entradas.map(([clave, valor], indice) => {
        const alto = proporcion(valor, tope);
        let clases = "rep-barras__barra";
        if (alto === 0) {
          clases += " rep-barras__barra--vacia";
        } else if (esNegativo(valor)) {
          clases += " rep-barras__barra--negativa";
        }
        return (
          <li key={clave} className="rep-barras__col" title={(detallar ?? nombrar)(clave)}>
            <span className="rep-barras__monto">$ {formatearNumero(valor)}</span>
            <span className={clases} style={estiloDeBarra({ height: `${alto}%` }, indice)} />
            <span className="rep-barras__x">{nombrar(clave)}</span>
          </li>
        );
      })}
    </ul>
  );
}

export function Distribucion({
  datos,
  vacio,
  nombrar,
  detallar,
  notaUnica,
  secundario,
}: PropsDeDistribucion): JSX.Element {
  const entradas = Object.entries(datos);
  const primera = entradas[0];
  if (primera === undefined) {
    return <p className="rep-vacio">{vacio}</p>;
  }
  if (entradas.length < MINIMO_PARA_COMPARAR) {
    return (
      <DatoUnico
        rotulo={
          secundario === undefined
            ? (detallar ?? nombrar)(primera[0])
            : `${(detallar ?? nombrar)(primera[0])} · ${secundario(primera[0])}`
        }
        monto={primera[1]}
        nota={notaUnica}
      />
    );
  }

  const total = sumaDe(entradas.map(([, valor]) => valor));

  return (
    <ul className="rep-dist">
      {entradas.map(([clave, valor], indice) => {
        const parte = proporcion(valor, total);
        return (
          <li key={clave} className="rep-dist__fila">
            <span className="rep-dist__sw" aria-hidden="true" />
            <span>
              <span className="rep-dist__nombre">{nombrar(clave)}</span>
              {secundario !== undefined && (
                <span className="rep-dist__secundario">{secundario(clave)}</span>
              )}
              <span className="rep-dist__pista">
                <span
                  className="rep-dist__barra"
                  style={estiloDeBarra({ width: `${parte}%` }, indice)}
                />
              </span>
            </span>
            <span className="rep-dist__cifras">
              <span className="rep-dist__monto">$ {formatearNumero(valor)}</span>
              {/* Redondeado a entero: son cuatro categorías, no un balance, y «33 %» se lee
                  de un vistazo donde «33,33 %» obliga a leer. Por el redondeo las partes
                  pueden sumar 99 o 101; el importe de al lado es el dato exacto. */}
              <span className="rep-dist__parte">{Math.round(parte)} %</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}
