/**
 * Data table — specification §1.3 ("Tablas") and the prototype's `.table`.
 *
 * Generic over the row type so a screen declares what it is listing and the column
 * definitions are checked against it. A table of `unknown` would accept a column reading
 * a field that does not exist, which is the bug this shape prevents at compile time.
 *
 * **`vacia` is not decoration.** A table that renders zero rows and nothing else looks
 * like a screen that failed to load. The specification asks for an explicit empty state
 * and this makes it impossible to forget.
 */

import type { ReactNode } from "react";

export interface Columna<T> {
  readonly clave: string;
  readonly titulo: string;
  readonly celda: (fila: T) => ReactNode;
  /** Right-aligned, for the actions column. */
  readonly alDerecha?: boolean;
}

export interface PropsDeTabla<T> {
  readonly titulo: string;
  readonly columnas: readonly Columna<T>[];
  readonly filas: readonly T[];
  readonly claveDeFila: (fila: T) => string;
  readonly vacia: string;
}

export function Tabla<T>({
  titulo,
  columnas,
  filas,
  claveDeFila,
  vacia,
}: PropsDeTabla<T>): JSX.Element {
  if (filas.length === 0) {
    return <p className="tabla__vacia">{vacia}</p>;
  }

  return (
    <div className="tabla__contenedor">
      <table className="tabla">
        <caption className="tabla__caption">{titulo}</caption>
        <thead>
          <tr>
            {columnas.map((columna) => (
              <th
                key={columna.clave}
                scope="col"
                className={columna.alDerecha === true ? "tabla__celda--derecha" : undefined}
              >
                {columna.titulo}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {filas.map((fila) => (
            <tr key={claveDeFila(fila)}>
              {columnas.map((columna) => (
                <td
                  key={columna.clave}
                  className={columna.alDerecha === true ? "tabla__celda--derecha" : undefined}
                >
                  {columna.celda(fila)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
