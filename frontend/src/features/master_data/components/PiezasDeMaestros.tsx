/**
 * Las piezas de presentación que comparten Servicios y Categorías.
 *
 * Clientes tiene las suyas (`FilaDeCliente`, `HerramientasDeClientes`, `VacioDeClientes`) y no se
 * tocan; estas tres son el mismo lenguaje —azulejo de color estable, buscador con lupa, vacío con
 * icono— para las dos pantallas que no tienen avatar de iniciales. Ninguna sabe nada de la red.
 */

"use client";

import type { CSSProperties, ReactNode } from "react";

import { tonoDe } from "./FilaDeCliente";
import { IconoDeLimpiar, IconoDeLupa, IconoDeMas } from "./iconos";

/** El azulejo de icono de una fila: mismo criterio de color que el avatar (estable por nombre). */
export function AzulejoDeIcono({
  nombre,
  children,
}: {
  readonly nombre: string;
  readonly children: ReactNode;
}): JSX.Element {
  return (
    <span
      className="mae-azulejo"
      aria-hidden="true"
      style={{ "--mae-tono": tonoDe(nombre) } as CSSProperties}
    >
      {children}
    </span>
  );
}

export interface PropsDeBuscador {
  readonly id: string;
  readonly valor: string;
  readonly placeholder: string;
  readonly onCambio: (valor: string) => void;
}

/** Búsqueda con lupa y botón de limpiar; la etiqueta «Buscar» queda para el lector de pantalla. */
export function BuscadorConLupa({
  id,
  valor,
  placeholder,
  onCambio,
}: PropsDeBuscador): JSX.Element {
  return (
    <div className="mae-buscador">
      <label className="solo-lectores" htmlFor={id}>
        Buscar
      </label>
      <span className="mae-buscador__icono" aria-hidden="true">
        <IconoDeLupa />
      </span>
      <input
        id={id}
        type="search"
        className="mae-buscador__control"
        value={valor}
        placeholder={placeholder}
        autoComplete="off"
        onChange={(evento) => onCambio(evento.target.value)}
      />
      {valor !== "" && (
        <button
          type="button"
          className="mae-buscador__limpiar"
          aria-label="Limpiar búsqueda"
          onClick={() => onCambio("")}
        >
          <IconoDeLimpiar />
        </button>
      )}
    </div>
  );
}

export interface PropsDeVacioGenerico {
  readonly icono: ReactNode;
  readonly hayFiltros: boolean;
  readonly puedeEditar: boolean;
  readonly titulo: string;
  readonly texto: string;
  readonly tituloFiltrado: string;
  readonly etiquetaDeNuevo: string;
  readonly onNuevo: () => void;
  readonly onLimpiar: () => void;
}

/** Dos vacíos distintos: el catálogo sin nada (crear el primero) y el filtro sin resultados. */
export function VacioDeMaestros({
  icono,
  hayFiltros,
  puedeEditar,
  titulo,
  texto,
  tituloFiltrado,
  etiquetaDeNuevo,
  onNuevo,
  onLimpiar,
}: PropsDeVacioGenerico): JSX.Element {
  return (
    <div className="mae-vacio">
      <span className="mae-vacio__icono" aria-hidden="true">
        {icono}
      </span>
      <p className="mae-vacio__titulo">{hayFiltros ? tituloFiltrado : titulo}</p>
      <p className="mae-vacio__texto">
        {hayFiltros ? "Probá con otra búsqueda o quitá algún filtro." : texto}
      </p>
      {hayFiltros ? (
        <button type="button" className="mae-vacio__accion" onClick={onLimpiar}>
          Limpiar filtros
        </button>
      ) : (
        puedeEditar && (
          <button type="button" className="mae-cta mae-cta--compacto" onClick={onNuevo}>
            <span className="mae-cta__icono" aria-hidden="true">
              <IconoDeMas />
            </span>
            {etiquetaDeNuevo}
          </button>
        )
      )}
    </div>
  );
}
