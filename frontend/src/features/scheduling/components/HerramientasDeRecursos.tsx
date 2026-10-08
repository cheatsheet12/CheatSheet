/**
 * La barra de herramientas del listado de recursos: búsqueda por nombre, chips de tipo y de
 * estado, y cuántos hay.
 *
 * Todo en una tarjeta, como en Clientes y Servicios. No sabe nada de la red: recibe el valor de
 * cada filtro y avisa cuando cambia. Los chips son botones con `aria-pressed`, agrupados con su
 * nombre para el lector de pantalla.
 */

"use client";

import { Search, X } from "lucide-react";

export type FiltroDeTipo = "" | "PERSONA" | "ESPACIO" | "EQUIPO";
export type FiltroDeEstado = "" | "activos" | "inactivos";

const TIPOS: readonly { valor: FiltroDeTipo; etiqueta: string }[] = [
  { valor: "", etiqueta: "Todos" },
  { valor: "PERSONA", etiqueta: "Personas" },
  { valor: "ESPACIO", etiqueta: "Espacios" },
  { valor: "EQUIPO", etiqueta: "Equipos" },
];

const ESTADOS: readonly { valor: FiltroDeEstado; etiqueta: string }[] = [
  { valor: "", etiqueta: "Todos" },
  { valor: "activos", etiqueta: "Activos" },
  { valor: "inactivos", etiqueta: "Inactivos" },
];

export interface PropsDeHerramientasDeRecursos {
  readonly texto: string;
  readonly tipo: FiltroDeTipo;
  readonly estado: FiltroDeEstado;
  readonly total: number;
  readonly onTexto: (valor: string) => void;
  readonly onTipo: (valor: FiltroDeTipo) => void;
  readonly onEstado: (valor: FiltroDeEstado) => void;
}

function Chips<T extends string>({
  nombre,
  opciones,
  valor,
  onElegir,
}: {
  readonly nombre: string;
  readonly opciones: readonly { valor: T; etiqueta: string }[];
  readonly valor: T;
  readonly onElegir: (valor: T) => void;
}): JSX.Element {
  return (
    <div className="age-filtro" role="group" aria-label={nombre}>
      {opciones.map((opcion) => (
        <button
          key={opcion.valor}
          type="button"
          className="age-filtro__chip"
          aria-pressed={valor === opcion.valor}
          onClick={() => onElegir(opcion.valor)}
        >
          {opcion.etiqueta}
        </button>
      ))}
    </div>
  );
}

export function HerramientasDeRecursos({
  texto,
  tipo,
  estado,
  total,
  onTexto,
  onTipo,
  onEstado,
}: PropsDeHerramientasDeRecursos): JSX.Element {
  return (
    <div className="age-herramientas" role="search">
      <div className="age-buscador">
        <label className="solo-lectores" htmlFor="age-buscador-recursos">
          Buscar
        </label>
        <span className="age-buscador__icono" aria-hidden="true">
          <Search />
        </span>
        <input
          id="age-buscador-recursos"
          type="search"
          className="age-buscador__control"
          value={texto}
          placeholder="Buscar por nombre"
          autoComplete="off"
          onChange={(evento) => onTexto(evento.target.value)}
        />
        {texto !== "" && (
          <button
            type="button"
            className="age-buscador__limpiar"
            aria-label="Limpiar búsqueda"
            onClick={() => onTexto("")}
          >
            <X aria-hidden="true" />
          </button>
        )}
      </div>
      <Chips nombre="Tipo de recurso" opciones={TIPOS} valor={tipo} onElegir={onTipo} />
      <Chips nombre="Estado" opciones={ESTADOS} valor={estado} onElegir={onEstado} />
      <p className="age-herramientas__cuenta" aria-live="polite">
        {`${total} ${total === 1 ? "recurso" : "recursos"}`}
      </p>
    </div>
  );
}
