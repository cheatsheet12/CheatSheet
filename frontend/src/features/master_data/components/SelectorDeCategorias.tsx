/**
 * The classification control, shared by PAN-DM-01 and PAN-DM-02 (HU-E4-04).
 *
 * A checkbox per category, because RN-02 lets an element carry several and a `<select>`
 * would suggest otherwise. Each toggle is one call: RN-03 describes the assignment as
 * immediate, so there is no "save" step to forget.
 *
 * **It only offers what fits.** The list comes from `listarCategorias(ambito)`, which the
 * backend already filters by usability — asking for `CLIENTE` returns the `AMBOS` ones
 * too. That is the acceptance criterion «el sistema no ofrece esa categoría para ese
 * elemento», satisfied by asking the right question instead of filtering here.
 *
 * **It appears only when editing**, never when creating: an assignment needs an element
 * that already has an id. You create, then classify.
 */

"use client";

import { useEffect, useState } from "react";

import { Alert } from "@/shared";

import { listarCategorias } from "../api/categoria";
import type { AmbitoDeCategoria, Categoria } from "../api/categoria";

export interface PropsDeSelector {
  readonly ambito: AmbitoDeCategoria;
  /** The ones the element already carries. */
  readonly asignadas: readonly Categoria[];
  readonly onAlternar: (categoriaId: string, asignar: boolean) => Promise<void>;
}

export function SelectorDeCategorias({
  ambito,
  asignadas,
  onAlternar,
}: PropsDeSelector): JSX.Element {
  const [disponibles, setDisponibles] = useState<readonly Categoria[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [cargado, setCargado] = useState(false);

  useEffect(() => {
    let vigente = true;
    listarCategorias(ambito)
      .then((listado) => {
        if (vigente) {
          setDisponibles(listado.categorias);
          setCargado(true);
        }
      })
      .catch(() => {
        if (vigente) {
          setError("No se pudieron cargar las categorias.");
          setCargado(true);
        }
      });
    return () => {
      vigente = false;
    };
  }, [ambito]);

  const asignadasIds = new Set(asignadas.map((categoria) => categoria.id));

  if (error !== null) {
    return <Alert tono="advertencia">{error}</Alert>;
  }
  if (cargado && disponibles.length === 0) {
    return <p className="dm-selector__vacio">No hay categorias para este tipo de elemento.</p>;
  }

  return (
    <fieldset className="dm-selector">
      <legend>Categorias</legend>
      {disponibles.map((categoria) => (
        <label key={categoria.id} className="dm-selector__opcion">
          <input
            type="checkbox"
            checked={asignadasIds.has(categoria.id)}
            onChange={(evento) => void onAlternar(categoria.id, evento.target.checked)}
          />
          {categoria.nombre}
        </label>
      ))}
    </fieldset>
  );
}
