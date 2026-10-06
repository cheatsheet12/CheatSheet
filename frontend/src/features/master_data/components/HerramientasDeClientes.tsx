/**
 * La barra de herramientas del listado de clientes: búsqueda, filtros y cuántos hay.
 *
 * Es una sola tarjeta compacta y no tres campos sueltos: lo que se mira después de tocar un
 * filtro es el contador, y tiene que estar en el mismo renglón que el filtro.
 *
 * No sabe nada de la red. Recibe el valor de cada filtro y avisa cuando cambia; quien llama es
 * el que recarga. Las etiquetas de «Origen» y «Categoría» están en el DOM —ocultas a la vista—
 * porque un `<select>` sin etiqueta es un control mudo para un lector de pantalla.
 */

"use client";

import { Select } from "@/shared";

import type { Categoria } from "../api/categoria";
import { IconoDeLimpiar, IconoDeLupa } from "./iconos";

const ORIGENES: readonly { valor: string; etiqueta: string }[] = [
  { valor: "", etiqueta: "Todos los orígenes" },
  { valor: "PANEL", etiqueta: "Panel" },
  { valor: "PLANILLA", etiqueta: "Planilla" },
  { valor: "AGENTE", etiqueta: "Agente" },
];

export interface PropsDeHerramientas {
  readonly texto: string;
  readonly origen: string;
  readonly categoria: string;
  readonly soloActivos: boolean;
  readonly categorias: readonly Categoria[];
  readonly total: number;
  readonly onTexto: (valor: string) => void;
  readonly onOrigen: (valor: string) => void;
  readonly onCategoria: (valor: string) => void;
  readonly onSoloActivos: (valor: boolean) => void;
}

export function HerramientasDeClientes({
  texto,
  origen,
  categoria,
  soloActivos,
  categorias,
  total,
  onTexto,
  onOrigen,
  onCategoria,
  onSoloActivos,
}: PropsDeHerramientas): JSX.Element {
  return (
    <div className="mae-herramientas" role="search">
      <div className="mae-buscador">
        <label className="solo-lectores" htmlFor="dm-buscador">
          Buscar
        </label>
        <span className="mae-buscador__icono" aria-hidden="true">
          <IconoDeLupa />
        </span>
        <input
          id="dm-buscador"
          type="search"
          className="mae-buscador__control"
          value={texto}
          placeholder="Buscar por nombre o CUIT"
          autoComplete="off"
          onChange={(evento) => onTexto(evento.target.value)}
        />
        {texto !== "" && (
          <button
            type="button"
            className="mae-buscador__limpiar"
            aria-label="Limpiar búsqueda"
            onClick={() => onTexto("")}
          >
            <IconoDeLimpiar />
          </button>
        )}
      </div>
      <Select
        id="dm-origen"
        etiqueta="Origen"
        etiquetaOculta
        opciones={ORIGENES}
        value={origen}
        onChange={(evento) => onOrigen(evento.target.value)}
      />
      <Select
        id="dm-categoria"
        etiqueta="Categoría"
        etiquetaOculta
        opciones={[
          { valor: "", etiqueta: "Todas las categorías" },
          ...categorias.map((c) => ({ valor: c.id, etiqueta: c.nombre })),
        ]}
        value={categoria}
        onChange={(evento) => onCategoria(evento.target.value)}
      />
      <label className="mae-interruptor" htmlFor="dm-solo-activos">
        <input
          id="dm-solo-activos"
          type="checkbox"
          role="switch"
          className="mae-interruptor__control"
          checked={soloActivos}
          onChange={(evento) => onSoloActivos(evento.target.checked)}
        />
        Solo activos
      </label>
      <p className="mae-herramientas__cuenta" aria-live="polite">
        {`${total} ${total === 1 ? "cliente" : "clientes"}`}
      </p>
    </div>
  );
}
