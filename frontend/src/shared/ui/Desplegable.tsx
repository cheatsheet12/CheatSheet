/**
 * Disclosure / accordion: a header that folds and unfolds its content.
 *
 * El contenido secundario o largo (el detalle de un listado, una explicación) se pliega
 * para que la pantalla muestre primero lo que se busca. Cerrado, el contenido sigue en el
 * DOM pero fuera del orden de foco; la altura se anima con CSS, sin medir nada.
 *
 * `Desplegable.Grupo` hace de acordeón exclusivo: abrir uno cierra el que estaba abierto.
 */

"use client";

import { createContext, useContext, useId, useState } from "react";
import type { ReactNode } from "react";

import "@/shared/ui/desplegable.css";

export type VarianteDeDesplegable = "tarjeta" | "simple";

export interface PropsDeDesplegable {
  readonly titulo: ReactNode;
  readonly children: ReactNode;
  /** Short text at the right of the title, e.g. a count. */
  readonly resumen?: ReactNode;
  readonly variante?: VarianteDeDesplegable;
  readonly abiertoAlInicio?: boolean;
  /** Identifies the item inside a `Desplegable.Grupo`; defaults to a generated id. */
  readonly valor?: string;
}

export interface PropsDeGrupo {
  readonly children: ReactNode;
  /** The item open at first, by its `valor`. */
  readonly abiertoAlInicio?: string;
}

interface ContextoDeGrupo {
  readonly abierto: string | null;
  readonly alternar: (valor: string) => void;
}

const ContextoGrupo = createContext<ContextoDeGrupo | null>(null);

function Chevron(): JSX.Element {
  return (
    <svg
      className="desplegable__chevron"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M3.5 6l4.5 4.5L12.5 6" />
    </svg>
  );
}

function Grupo({ children, abiertoAlInicio }: PropsDeGrupo): JSX.Element {
  const [abierto, setAbierto] = useState<string | null>(abiertoAlInicio ?? null);
  const contexto: ContextoDeGrupo = {
    abierto,
    alternar: (valor) => setAbierto((actual) => (actual === valor ? null : valor)),
  };
  return (
    <ContextoGrupo.Provider value={contexto}>
      <div className="desplegable-grupo">{children}</div>
    </ContextoGrupo.Provider>
  );
}

export function Desplegable({
  titulo,
  children,
  resumen,
  variante = "tarjeta",
  abiertoAlInicio = false,
  valor,
}: PropsDeDesplegable): JSX.Element {
  const idGenerado = useId();
  const grupo = useContext(ContextoGrupo);
  const [abiertoPropio, setAbiertoPropio] = useState(abiertoAlInicio);
  const clave = valor ?? idGenerado;
  const abierto = grupo === null ? abiertoPropio : grupo.abierto === clave;

  function alternar(): void {
    if (grupo === null) {
      setAbiertoPropio((actual) => !actual);
    } else {
      grupo.alternar(clave);
    }
  }

  const idBoton = `${idGenerado}-boton`;
  const idPanel = `${idGenerado}-panel`;

  return (
    <div
      className={`desplegable desplegable--${variante}${abierto ? " desplegable--abierto" : ""}`}
    >
      <h3 className="desplegable__titulo">
        <button
          type="button"
          id={idBoton}
          className="desplegable__boton"
          aria-expanded={abierto}
          aria-controls={idPanel}
          onClick={alternar}
        >
          <span>{titulo}</span>
          {resumen !== undefined && <span className="desplegable__resumen">{resumen}</span>}
          <Chevron />
        </button>
      </h3>
      <div id={idPanel} role="region" aria-labelledby={idBoton} className="desplegable__panel">
        <div className="desplegable__recorte">
          <div className="desplegable__contenido">{children}</div>
        </div>
      </div>
    </div>
  );
}

Desplegable.Grupo = Grupo;
