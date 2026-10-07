/**
 * Las piezas del flujo de «Nueva emisión»: el indicador de progreso, la tarjeta de cada paso y el
 * panel que se pliega.
 *
 * El estado de un paso es uno de tres —pendiente, activo, completo— y es lo único que decide
 * cómo se ve: el pendiente se atenúa y dice qué lo desbloquea, el activo se pone en foco y el
 * completo muestra un tilde. La altura se anima con `grid-template-rows` (de `0fr` a `1fr`) y no
 * con `height`, que no se puede animar hacia `auto`.
 */

import type { ReactNode } from "react";

import { IconoDeCandado, IconoDeTilde } from "./iconosEmision";

export type EstadoDePaso = "pendiente" | "activo" | "completo";

const PALABRA_DE_ESTADO: Readonly<Record<EstadoDePaso, string>> = {
  pendiente: "Pendiente",
  activo: "En curso",
  completo: "Completo",
};

export interface DatosDePaso {
  readonly titulo: string;
  readonly estado: EstadoDePaso;
}

export function IndicadorDePasos({
  pasos,
}: {
  readonly pasos: readonly DatosDePaso[];
}): JSX.Element {
  return (
    <ol className="fac-em-progreso" aria-label="Progreso de la emisión">
      {pasos.map((paso, indice) => (
        <li
          key={paso.titulo}
          className={`fac-em-progreso__paso fac-em-progreso__paso--${paso.estado}`}
          aria-current={paso.estado === "activo" ? "step" : undefined}
        >
          <span className="fac-em-progreso__nodo" aria-hidden="true">
            {paso.estado === "completo" ? <IconoDeTilde /> : indice + 1}
          </span>
          <span className="fac-em-progreso__texto">
            <b>{paso.titulo}</b>
            <small>{PALABRA_DE_ESTADO[paso.estado]}</small>
          </span>
        </li>
      ))}
    </ol>
  );
}

/** Un panel que se pliega sin saltos. Plegado queda fuera del orden de tabulación. */
export function Colapsable({
  abierto,
  children,
}: {
  readonly abierto: boolean;
  readonly children: ReactNode;
}): JSX.Element {
  return (
    <div className={`fac-em-colapsable${abierto ? " fac-em-colapsable--abierto" : ""}`}>
      <div className="fac-em-colapsable__interior">{children}</div>
    </div>
  );
}

export interface PropsDePasoDeEmision {
  readonly numero: number;
  readonly titulo: string;
  readonly estado: EstadoDePaso;
  /** Una frase de lo que hace este paso, cuando está activo. */
  readonly ayuda: string;
  /** Qué lo desbloquea, mientras está pendiente. */
  readonly motivoDeBloqueo: string;
  /** A la derecha del título: un resumen, una pastilla o el botón «Cambiar». */
  readonly extremo?: ReactNode;
  readonly children: ReactNode;
}

export function PasoDeEmision({
  numero,
  titulo,
  estado,
  ayuda,
  motivoDeBloqueo,
  extremo,
  children,
}: PropsDePasoDeEmision): JSX.Element {
  const idTitulo = `fac-em-paso-${numero}`;
  return (
    <section
      className={`fac-em-paso fac-em-paso--${estado}`}
      aria-labelledby={idTitulo}
      aria-disabled={estado === "pendiente" ? true : undefined}
    >
      <header className="fac-em-paso__cabecera">
        <span className="fac-em-paso__nodo" aria-hidden="true">
          {estado === "completo" ? <IconoDeTilde /> : numero}
        </span>
        <div className="fac-em-paso__titulos">
          <h2 id={idTitulo} className="fac-em-paso__titulo">
            {titulo}
          </h2>
          {estado === "pendiente" ? (
            <p className="fac-em-paso__ayuda fac-em-paso__ayuda--bloqueo">
              <IconoDeCandado />
              {motivoDeBloqueo}
            </p>
          ) : (
            estado === "activo" && <p className="fac-em-paso__ayuda">{ayuda}</p>
          )}
        </div>
        {extremo !== undefined && <div className="fac-em-paso__extremo">{extremo}</div>}
      </header>
      {estado !== "pendiente" && <div className="fac-em-paso__cuerpo">{children}</div>}
    </section>
  );
}
