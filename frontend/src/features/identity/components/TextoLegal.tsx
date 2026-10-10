/**
 * Draws a legal text written in a small Markdown subset (HU-E1-08 RN-01).
 *
 * The subset is exactly three things: `## ` headings, paragraphs (consecutive lines joined,
 * a blank line separates them) and `- ` lists. Everything else is plain text.
 *
 * **It builds React elements and nothing else.** No `dangerouslySetInnerHTML` and no
 * Markdown dependency: a text that is reviewed in a pull request and published for the
 * whole internet must not be able to carry markup, so `<script>` in a text shows up as the
 * characters `<script>` and not as an element.
 */

import type { ReactNode } from "react";

type Bloque =
  | { readonly tipo: "titulo"; readonly texto: string }
  | { readonly tipo: "parrafo"; readonly texto: string }
  | { readonly tipo: "lista"; readonly items: readonly string[] };

const PREFIJO_DE_TITULO = "## ";
const PREFIJO_DE_ITEM = "- ";

/** Splits the text into blocks, line by line. */
function aBloques(texto: string): readonly Bloque[] {
  const bloques: Bloque[] = [];
  let parrafo: string[] = [];
  let items: string[] = [];

  const cerrar = (): void => {
    if (parrafo.length > 0) {
      bloques.push({ tipo: "parrafo", texto: parrafo.join(" ") });
      parrafo = [];
    }
    if (items.length > 0) {
      bloques.push({ tipo: "lista", items });
      items = [];
    }
  };

  for (const crudo of texto.split("\n")) {
    const linea = crudo.trim();
    if (linea === "") {
      cerrar();
    } else if (linea.startsWith(PREFIJO_DE_TITULO)) {
      cerrar();
      bloques.push({ tipo: "titulo", texto: linea.slice(PREFIJO_DE_TITULO.length) });
    } else if (linea.startsWith(PREFIJO_DE_ITEM)) {
      if (parrafo.length > 0) cerrar();
      items.push(linea.slice(PREFIJO_DE_ITEM.length));
    } else {
      if (items.length > 0) cerrar();
      parrafo.push(linea);
    }
  }
  cerrar();
  return bloques;
}

function dibujar(bloque: Bloque, indice: number): ReactNode {
  switch (bloque.tipo) {
    case "titulo":
      return (
        <h2 key={indice} className="legal__titulo">
          {bloque.texto}
        </h2>
      );
    case "parrafo":
      return <p key={indice}>{bloque.texto}</p>;
    case "lista":
      return (
        <ul key={indice}>
          {bloque.items.map((item, posicion) => (
            <li key={posicion}>{item}</li>
          ))}
        </ul>
      );
  }
}

export function TextoLegal({ texto }: { readonly texto: string }): JSX.Element {
  return <div className="legal__texto">{aBloques(texto).map(dibujar)}</div>;
}
