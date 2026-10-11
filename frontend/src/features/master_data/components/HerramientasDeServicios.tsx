/**
 * La barra de herramientas del listado de servicios: búsqueda, filtros y cuántos hay.
 *
 * Misma tarjeta que la de Clientes. No sabe nada de la red: recibe el valor de cada filtro y avisa
 * cuando cambia. Las etiquetas de los selectores están en el DOM, ocultas a la vista.
 */

"use client";

import { Select } from "@/shared";

import type { Categoria } from "../api/categoria";
import { BuscadorConLupa } from "./PiezasDeMaestros";

const AGENDABLE: readonly { valor: string; etiqueta: string }[] = [
  { valor: "", etiqueta: "Agendables y no agendables" },
  { valor: "true", etiqueta: "Solo agendables" },
  { valor: "false", etiqueta: "Solo no agendables" },
];

export interface PropsDeHerramientasDeServicios {
  readonly texto: string;
  readonly agendable: string;
  readonly categoria: string;
  readonly soloActivos: boolean;
  readonly categorias: readonly Categoria[];
  readonly total: number;
  readonly onTexto: (valor: string) => void;
  readonly onAgendable: (valor: string) => void;
  readonly onCategoria: (valor: string) => void;
  readonly onSoloActivos: (valor: boolean) => void;
}

export function HerramientasDeServicios({
  texto,
  agendable,
  categoria,
  soloActivos,
  categorias,
  total,
  onTexto,
  onAgendable,
  onCategoria,
  onSoloActivos,
}: PropsDeHerramientasDeServicios): JSX.Element {
  return (
    <div className="mae-herramientas" role="search">
      <BuscadorConLupa
        id="dm-buscador-servicios"
        valor={texto}
        placeholder="Buscar por nombre"
        onCambio={onTexto}
      />
      <Select
        id="dm-agendable"
        etiqueta="Agendables"
        etiquetaOculta
        opciones={AGENDABLE}
        value={agendable}
        onChange={(evento) => onAgendable(evento.target.value)}
      />
      <Select
        id="dm-categoria-servicios"
        etiqueta="Categoría"
        etiquetaOculta
        opciones={[
          { valor: "", etiqueta: "Todas las categorías" },
          ...categorias.map((c) => ({ valor: c.id, etiqueta: c.nombre })),
        ]}
        value={categoria}
        onChange={(evento) => onCategoria(evento.target.value)}
      />
      <label className="mae-interruptor" htmlFor="dm-servicios-activos">
        <input
          id="dm-servicios-activos"
          type="checkbox"
          role="switch"
          className="mae-interruptor__control"
          checked={soloActivos}
          onChange={(evento) => onSoloActivos(evento.target.checked)}
        />
        Solo activos
      </label>
      <p className="mae-herramientas__cuenta" aria-live="polite">
        {`${total} ${total === 1 ? "servicio" : "servicios"}`}
      </p>
    </div>
  );
}
