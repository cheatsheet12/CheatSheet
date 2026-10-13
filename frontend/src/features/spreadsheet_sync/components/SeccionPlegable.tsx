/**
 * Una sección de la pantalla de ingesta que se puede esconder.
 *
 * La pantalla junta tres cosas —traer una planilla, las planillas que ya están vinculadas y el
 * historial de cargas— y quien viene a una sola de ellas no tiene por qué scrollear las otras
 * dos. Cada sección es una «pestaña» de encabezado fijo: el icono, el título, un contador y un
 * chevron; al tocarla, el contenido se pliega y queda sólo el encabezado.
 *
 * **Escondido no es borrado.** El contenido sigue en el DOM, así que un arrastre en curso o un
 * estado local no se pierden al plegar, pero sale del orden de foco y del árbol de accesibilidad
 * (`visibility`) cuando termina de cerrarse. La altura se anima con `grid-template-rows`, que no
 * necesita medir nada.
 */

"use client";

import { useId, useState } from "react";
import type { ReactNode } from "react";

import { ChevronDown } from "lucide-react";

import { Icono } from "./iconos";
import type { NombreDeIcono } from "./iconos";

export interface PropsDeSeccionPlegable {
  readonly titulo: string;
  readonly subtitulo: string;
  readonly icono: NombreDeIcono;
  /** Cuántos elementos tiene la sección: se ve aunque esté cerrada. */
  readonly cantidad?: number;
  readonly abiertaAlInicio?: boolean;
  readonly children: ReactNode;
}

export function SeccionPlegable({
  titulo,
  subtitulo,
  icono,
  cantidad,
  abiertaAlInicio = true,
  children,
}: PropsDeSeccionPlegable): JSX.Element {
  const id = useId();
  const [abierta, setAbierta] = useState(abiertaAlInicio);

  return (
    <section className="ing-pestana ing-bloque" data-abierta={abierta}>
      <h2 className="ing-pestana__titulo">
        <button
          type="button"
          className="ing-pestana__boton"
          aria-expanded={abierta}
          aria-controls={`${id}-panel`}
          onClick={() => {
            setAbierta((actual) => !actual);
          }}
        >
          <span className="ing-pestana__ico" aria-hidden="true">
            <Icono nombre={icono} />
          </span>
          <span className="ing-pestana__textos">
            <span className="ing-pestana__nombre">{titulo}</span>
            <span className="ing-pestana__sub">{subtitulo}</span>
          </span>
          {cantidad !== undefined && (
            <span className="ing-pestana__cuenta" aria-label={`${cantidad} en total`}>
              {cantidad}
            </span>
          )}
          <ChevronDown
            className="ing-pestana__chevron"
            size={18}
            strokeWidth={2}
            aria-hidden="true"
          />
        </button>
      </h2>
      <div id={`${id}-panel`} className="ing-pestana__panel" role="region" aria-label={titulo}>
        <div className="ing-pestana__recorte">
          <div className="ing-pestana__contenido">{children}</div>
        </div>
      </div>
    </section>
  );
}
