/**
 * El selector de período de PAN-REP-01 y de PAN-DSH-01.
 *
 * Una sola pieza para las dos pantallas: «las mismas cifras» (HU-E10-01 RN-06) sólo se sostiene
 * si las dos eligen el período de la misma manera. No sabe qué hacer con el cambio: lo avisa, y
 * cada pantalla decide si pide el tablero por `fetch` (Reportes) o escribe la URL (Inicio).
 */

"use client";

import { Campo } from "@/shared";

import type { RangoDePeriodo } from "../api/reporte";

export interface PropsDeSelectorDePeriodo {
  /** Lo que el usuario pidió: los dos campos. */
  readonly rango: RangoDePeriodo;
  /** El rango que efectivamente contestó el backend, ya en el formato del panel. */
  readonly resumen: string;
  readonly alCambiar: (cambios: RangoDePeriodo) => void;
}

export function SelectorDePeriodo({
  rango,
  resumen,
  alCambiar,
}: PropsDeSelectorDePeriodo): JSX.Element {
  return (
    <div className="rep-periodo">
      <p className="rep-periodo__titulo">Período</p>
      <div className="rep-filtros">
        <Campo
          id="rep-desde"
          etiqueta="Desde"
          type="date"
          value={rango.desde ?? ""}
          onChange={(evento) => alCambiar({ desde: evento.target.value })}
        />
        <Campo
          id="rep-hasta"
          etiqueta="Hasta"
          type="date"
          value={rango.hasta ?? ""}
          onChange={(evento) => alCambiar({ hasta: evento.target.value })}
        />
      </div>
      {/* El rango que efectivamente contestó el backend, en el formato del resto del panel.
          Los dos campos de arriba muestran lo que el usuario pidió; esto, lo que se está
          viendo — y no son lo mismo mientras una consulta está en el aire. */}
      <p className="rep-periodo__resumen">{resumen}</p>
    </div>
  );
}
