/**
 * La barra de filtros del listado de cobros, en una sola tarjeta: los cortes de estado como
 * control segmentado, el rango de fechas con el calendario del panel, el `select` con los
 * siete estados del enum, «Limpiar filtros» cuando hay alguno y cuántos cobros se ven.
 *
 * Los segmentos y el `select` son el mismo filtro: los dos escriben `filtros.estado` y los dos
 * leen de ahí, así que no pueden mostrar cosas distintas. Los segmentos son el atajo a los
 * cortes que se miran todo el día; el `select` es el control que un lector de pantalla anuncia
 * con su etiqueta y el único que ofrece los estados de reembolso.
 *
 * **Sin contador en los segmentos.** El listado no trae cuántos cobros hay de cada estado, y
 * contar sobre las filas que llegaron para un solo filtro daría un «0» en los demás.
 *
 * No sabe nada de la red: avisa qué cambió y quien llama recarga.
 */

"use client";

import { X } from "lucide-react";

import { Select, SelectorDeFecha } from "@/shared";

import type { FiltrosDeCobro } from "../api/cobro";

/** Los siete estados del enum, con la etiqueta de interfaz de cada uno. */
export const ESTADOS: readonly { valor: string; etiqueta: string }[] = [
  { valor: "", etiqueta: "Todos los estados" },
  { valor: "APROBADO", etiqueta: "Pagado" },
  { valor: "PENDIENTE", etiqueta: "Pendiente" },
  { valor: "VENCIDO", etiqueta: "En mora" },
  { valor: "CANCELADO", etiqueta: "Cancelado" },
  { valor: "REEMBOLSADO_PARCIAL", etiqueta: "Reembolsado parcialmente" },
  { valor: "REEMBOLSADO", etiqueta: "Reembolsado" },
];

const SEGMENTOS: readonly { valor: string; etiqueta: string; tono: string }[] = [
  { valor: "", etiqueta: "Todos", tono: "" },
  { valor: "APROBADO", etiqueta: "Pagados", tono: "ok" },
  { valor: "PENDIENTE", etiqueta: "Pendientes", tono: "pendiente" },
  { valor: "VENCIDO", etiqueta: "En mora", tono: "mora" },
  { valor: "CANCELADO", etiqueta: "Cancelados", tono: "cancelado" },
];

export interface PropsDeHerramientasDeCobros {
  readonly filtros: FiltrosDeCobro;
  readonly total: number;
  readonly onCambiar: (cambios: FiltrosDeCobro) => void;
  readonly onLimpiar: () => void;
}

export function hayFiltrosActivos(filtros: FiltrosDeCobro): boolean {
  return (
    (filtros.estado ?? "") !== "" || (filtros.desde ?? "") !== "" || (filtros.hasta ?? "") !== ""
  );
}

export function HerramientasDeCobros({
  filtros,
  total,
  onCambiar,
  onLimpiar,
}: PropsDeHerramientasDeCobros): JSX.Element {
  return (
    <div className="cob-lst-herramientas" role="search">
      <div className="cob-lst-seg" role="group" aria-label="Filtros rápidos por estado">
        {SEGMENTOS.map((segmento) => (
          <button
            key={segmento.etiqueta}
            type="button"
            className="cob-lst-seg__opcion"
            aria-pressed={(filtros.estado ?? "") === segmento.valor}
            onClick={() => onCambiar({ estado: segmento.valor })}
          >
            {segmento.tono !== "" && (
              <span
                className={`cob-lst-seg__punto cob-lst-seg__punto--${segmento.tono}`}
                aria-hidden="true"
              />
            )}
            {segmento.etiqueta}
          </button>
        ))}
      </div>

      <div className="cob-lst-campos">
        <SelectorDeFecha
          id="cobros-desde"
          etiqueta="Desde"
          value={filtros.desde ?? ""}
          max={filtros.hasta || undefined}
          alCambiar={(valor) => onCambiar({ desde: valor })}
        />
        <SelectorDeFecha
          id="cobros-hasta"
          etiqueta="Hasta"
          value={filtros.hasta ?? ""}
          min={filtros.desde || undefined}
          alCambiar={(valor) => onCambiar({ hasta: valor })}
        />
        <Select
          id="cobros-estado"
          etiqueta="Estado"
          opciones={ESTADOS}
          value={filtros.estado ?? ""}
          onChange={(evento) => onCambiar({ estado: evento.target.value })}
        />
      </div>

      <div className="cob-lst-cierre">
        {hayFiltrosActivos(filtros) && (
          <button type="button" className="cob-lst-limpiar" onClick={onLimpiar}>
            <X size={14} strokeWidth={2.2} aria-hidden="true" />
            Limpiar filtros
          </button>
        )}
        <p className="cob-lst-cuenta" aria-live="polite">
          {`${total} ${total === 1 ? "cobro" : "cobros"}`}
        </p>
      </div>
    </div>
  );
}
