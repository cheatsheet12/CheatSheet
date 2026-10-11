/**
 * La barra de herramientas de la agenda, en una sola tarjeta: la vista (Lista, Semana, Día, Mes), la
 * navegación del período, los filtros y cuántos turnos hay.
 *
 * No sabe nada de la red: recibe los valores y avisa cuando cambian. Quien llama es el que
 * vuelve a pedir los turnos.
 *
 * **Desde y Hasta sólo se ofrecen en la vista Lista**, dentro de «Más filtros». En las vistas de
 * calendario el rango sale del período que se está mirando: dos controles que dijeran otra cosa
 * que la grilla serían una contradicción en pantalla.
 */

"use client";

import { useState } from "react";

import { Select, SelectorDeFecha } from "@/shared";
import type { ReactNode } from "react";

import type { FiltrosDeAgenda } from "../api/turno";
import type { VistaDeAgenda } from "./calendario";
import { rangoLegible } from "./calendario";
import {
  IconoDeDia,
  IconoDeFiltro,
  IconoDeFlecha,
  IconoDeLimpiar,
  IconoDeLista,
  IconoDeMes,
  IconoDeSemana,
} from "./iconos";

const ESTADOS: readonly { valor: string; etiqueta: string }[] = [
  { valor: "", etiqueta: "Todos los estados" },
  { valor: "RESERVADO", etiqueta: "Reservado" },
  { valor: "CONFIRMADO", etiqueta: "Confirmado" },
  { valor: "COMPLETADO", etiqueta: "Completado" },
  { valor: "NO_SHOW", etiqueta: "No se presentó" },
  { valor: "CANCELADO", etiqueta: "Cancelado" },
];

const VISTAS: readonly { valor: VistaDeAgenda; etiqueta: string; icono: ReactNode }[] = [
  { valor: "lista", etiqueta: "Lista", icono: <IconoDeLista /> },
  { valor: "semana", etiqueta: "Semana", icono: <IconoDeSemana /> },
  { valor: "dia", etiqueta: "Día", icono: <IconoDeDia /> },
  { valor: "mes", etiqueta: "Mes", icono: <IconoDeMes /> },
];

export interface PropsDeBarraDeAgenda {
  readonly vista: VistaDeAgenda;
  readonly ancla: string;
  readonly filtros: FiltrosDeAgenda;
  readonly recursos: readonly { readonly id: string; readonly nombre: string }[];
  readonly total: number;
  readonly onVista: (vista: VistaDeAgenda) => void;
  readonly onMover: (sentido: -1 | 1) => void;
  readonly onHoy: () => void;
  readonly onFiltros: (cambios: FiltrosDeAgenda) => void;
  readonly onLimpiar: () => void;
}

export function BarraDeAgenda({
  vista,
  ancla,
  filtros,
  recursos,
  total,
  onVista,
  onMover,
  onHoy,
  onFiltros,
  onLimpiar,
}: PropsDeBarraDeAgenda): JSX.Element {
  const hayFechas = Boolean(filtros.desde) || Boolean(filtros.hasta);
  const [abiertos, setAbiertos] = useState(false);
  const hayFiltros = Boolean(filtros.recurso_id) || Boolean(filtros.estado) || hayFechas;
  const enLista = vista === "lista";
  const masFiltros = enLista && (abiertos || hayFechas);

  return (
    <div className="age-barra" role="search" aria-label="Filtros de la agenda">
      <div className="age-barra__fila">
        <div className="age-segmentos" role="group" aria-label="Vista de la agenda">
          {VISTAS.map((una) => (
            <button
              key={una.valor}
              type="button"
              className="age-segmentos__opcion"
              aria-pressed={vista === una.valor}
              onClick={() => onVista(una.valor)}
            >
              <span className="age-segmentos__ico" aria-hidden="true">
                {una.icono}
              </span>
              {una.etiqueta}
            </button>
          ))}
        </div>

        {!enLista && (
          <div className="age-periodo">
            <button
              type="button"
              className="age-periodo__flecha"
              aria-label="Período anterior"
              onClick={() => onMover(-1)}
            >
              <IconoDeFlecha sentido="izquierda" />
            </button>
            <button type="button" className="age-periodo__hoy" onClick={onHoy}>
              Hoy
            </button>
            <button
              type="button"
              className="age-periodo__flecha"
              aria-label="Período siguiente"
              onClick={() => onMover(1)}
            >
              <IconoDeFlecha />
            </button>
            <p className="age-periodo__rango" aria-live="polite">
              {rangoLegible(vista, ancla)}
            </p>
          </div>
        )}

        <Select
          id="agenda-recurso"
          etiqueta="Recurso"
          etiquetaOculta
          opciones={[
            { valor: "", etiqueta: "Todos los recursos" },
            ...recursos.map((uno) => ({ valor: uno.id, etiqueta: uno.nombre })),
          ]}
          value={filtros.recurso_id ?? ""}
          onChange={(evento) => onFiltros({ recurso_id: evento.target.value })}
        />
        <Select
          id="agenda-estado"
          etiqueta="Estado"
          etiquetaOculta
          opciones={ESTADOS}
          value={filtros.estado ?? ""}
          onChange={(evento) => onFiltros({ estado: evento.target.value })}
        />

        {enLista && (
          <button
            type="button"
            className="age-barra__boton"
            aria-expanded={masFiltros}
            aria-controls="agenda-mas-filtros"
            onClick={() => setAbiertos(!masFiltros)}
          >
            <span className="age-barra__boton-ico" aria-hidden="true">
              <IconoDeFiltro />
            </span>
            Más filtros
          </button>
        )}
        {hayFiltros && (
          <button
            type="button"
            className="age-barra__boton age-barra__boton--limpiar"
            onClick={onLimpiar}
          >
            <span className="age-barra__boton-ico" aria-hidden="true">
              <IconoDeLimpiar />
            </span>
            Limpiar filtros
          </button>
        )}
        <p className="age-barra__cuenta" aria-live="polite">
          {total} {total === 1 ? "turno" : "turnos"}
        </p>
      </div>

      {masFiltros && (
        <div className="age-barra__mas" id="agenda-mas-filtros">
          <SelectorDeFecha
            id="agenda-desde"
            etiqueta="Desde"
            value={filtros.desde ?? ""}
            max={filtros.hasta || undefined}
            alCambiar={(valor) => onFiltros({ desde: valor })}
          />
          <SelectorDeFecha
            id="agenda-hasta"
            etiqueta="Hasta"
            value={filtros.hasta ?? ""}
            min={filtros.desde || undefined}
            alCambiar={(valor) => onFiltros({ hasta: valor })}
          />
        </div>
      )}
    </div>
  );
}
