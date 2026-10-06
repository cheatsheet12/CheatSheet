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

/** Un atajo: el nombre que ve la persona y cómo se calcula el rango a partir de «hoy». */
interface Atajo {
  readonly etiqueta: string;
  readonly rango: (hoy: Date) => { readonly desde: string; readonly hasta: string };
}

/** `YYYY-MM-DD` en hora local: `toISOString` corre el día cuando el huso no es UTC. */
function aIso(fecha: Date): string {
  const mes = String(fecha.getMonth() + 1).padStart(2, "0");
  const dia = String(fecha.getDate()).padStart(2, "0");
  return `${fecha.getFullYear()}-${mes}-${dia}`;
}

const ATAJOS: readonly Atajo[] = [
  {
    etiqueta: "Este mes",
    rango: (hoy) => ({
      desde: aIso(new Date(hoy.getFullYear(), hoy.getMonth(), 1)),
      hasta: aIso(new Date(hoy.getFullYear(), hoy.getMonth() + 1, 0)),
    }),
  },
  {
    etiqueta: "Mes pasado",
    rango: (hoy) => ({
      desde: aIso(new Date(hoy.getFullYear(), hoy.getMonth() - 1, 1)),
      hasta: aIso(new Date(hoy.getFullYear(), hoy.getMonth(), 0)),
    }),
  },
  {
    etiqueta: "Últimos 30 días",
    rango: (hoy) => ({
      desde: aIso(new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate() - 29)),
      hasta: aIso(hoy),
    }),
  },
  {
    etiqueta: "Este año",
    rango: (hoy) => ({
      desde: aIso(new Date(hoy.getFullYear(), 0, 1)),
      hasta: aIso(new Date(hoy.getFullYear(), 11, 31)),
    }),
  },
];

export function SelectorDePeriodo({
  rango,
  resumen,
  alCambiar,
}: PropsDeSelectorDePeriodo): JSX.Element {
  const hoy = new Date();
  return (
    <div className="rep-periodo">
      <div className="rep-periodo__cabecera">
        <p className="rep-periodo__titulo">Período</p>
        {/* El rango que efectivamente contestó el backend, en el formato del resto del panel.
            Los dos campos de abajo muestran lo que el usuario pidió; esto, lo que se está
            viendo — y no son lo mismo mientras una consulta está en el aire. */}
        <p className="rep-periodo__resumen">{resumen}</p>
      </div>
      <div className="rep-periodo__cuerpo">
        <div className="rep-filtros">
          <Campo
            id="rep-desde"
            etiqueta="Desde"
            type="date"
            value={rango.desde ?? ""}
            onChange={(evento) => alCambiar({ desde: evento.target.value })}
          />
          <span className="rep-periodo__flecha" aria-hidden="true">
            →
          </span>
          <Campo
            id="rep-hasta"
            etiqueta="Hasta"
            type="date"
            value={rango.hasta ?? ""}
            onChange={(evento) => alCambiar({ hasta: evento.target.value })}
          />
        </div>
        <div className="rep-periodo__atajos" role="group" aria-label="Atajos de período">
          {ATAJOS.map((atajo) => {
            const propio = atajo.rango(hoy);
            const activo = rango.desde === propio.desde && rango.hasta === propio.hasta;
            return (
              <button
                key={atajo.etiqueta}
                type="button"
                className={`rep-atajo${activo ? " rep-atajo--activo" : ""}`}
                aria-pressed={activo}
                onClick={() => alCambiar(propio)}
              >
                {atajo.etiqueta}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
