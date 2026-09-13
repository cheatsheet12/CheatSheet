/**
 * PAN-DM-03 — Datos Maestros · Categorías (HU-E4-03).
 *
 * The smallest of the three master-data screens, and the only one with a delete. The
 * confirmation HU-E4-03's fourth acceptance criterion asks for is a real dialog the action
 * raises before running — and the wording says what will happen, because «eliminar» on its
 * own does not tell anybody that their clients are about to lose a label.
 *
 * **El encabezado lo dibuja este componente**, como en sus dos hermanas: el CTA depende del
 * rol y abre el formulario, así que vive donde está el estado. Antes estaba metido en la fila
 * de filtros, al lado de un `<select>`, como si crear una categoría fuera filtrar por algo.
 *
 * **Las acciones de fila son texto**, y sólo la baja lleva el rojo — en la palabra, no en un
 * borde alrededor de la palabra.
 */

"use client";

import { useState } from "react";

import { Button, Modal, Select, Tabla } from "@/shared";
import type { Columna } from "@/shared";

import {
  ETIQUETAS_DE_AMBITO,
  ErrorDeCategoria,
  crearCategoria,
  editarCategoria,
  eliminarCategoria,
  listarCategorias,
} from "../api/categoria";
import type {
  AmbitoDeCategoria,
  Categoria,
  ListadoDeCategorias as Listado,
} from "../api/categoria";
import { FormularioDeCategoria } from "./FormularioDeCategoria";
import { IconoDeMas } from "./iconos";

const AMBITOS: readonly { valor: string; etiqueta: string }[] = (
  Object.keys(ETIQUETAS_DE_AMBITO) as AmbitoDeCategoria[]
).map((valor) => ({ valor, etiqueta: ETIQUETAS_DE_AMBITO[valor] }));

export interface PropsDeListadoDeCategorias {
  readonly inicial: Listado;
  readonly puedeEditar: boolean;
}

type Edicion = { readonly categoria: Categoria | undefined } | null;

export function ListadoDeCategorias({
  inicial,
  puedeEditar,
}: PropsDeListadoDeCategorias): JSX.Element {
  const [listado, setListado] = useState<Listado>(inicial);
  const [ambito, setAmbito] = useState("");
  const [edicion, setEdicion] = useState<Edicion>(null);
  const [error, setError] = useState<string | null>(null);

  const cuantas = listado.categorias.length;

  async function recargar(nuevoAmbito?: string): Promise<void> {
    const elegido = nuevoAmbito ?? ambito;
    setListado(await listarCategorias(elegido === "" ? undefined : (elegido as AmbitoDeCategoria)));
  }

  async function guardar(nombre: string, aplica_a: AmbitoDeCategoria): Promise<void> {
    setError(null);
    try {
      const existente = edicion?.categoria;
      if (existente === undefined) {
        await crearCategoria({ nombre, aplica_a });
      } else {
        await editarCategoria(existente.id, { nombre, aplica_a });
      }
      setEdicion(null);
      await recargar();
    } catch (fallo) {
      // El mensaje del backend es el texto de la historia: «Ya existe una categoria con
      // ese nombre en este ambito.»
      setError(
        fallo instanceof ErrorDeCategoria ? fallo.message : "No se pudo guardar la categoría.",
      );
    }
  }

  /**
   * El único borrado de toda la aplicación, y el cuarto criterio de aceptación pide que
   * pregunte antes.
   *
   * La pregunta la disparaba `Button variante="destructivo"`, que además pintaba la celda con
   * un borde rojo. Acá la acción es texto y la pregunta se hace a mano: es el mismo diálogo
   * modal, con la misma frase —que dice qué pierden los elementos y qué no—, sin la caja roja
   * repetida en cada renglón.
   */
  async function eliminar(categoria: Categoria): Promise<void> {
    if (
      !window.confirm(
        `¿Eliminar "${categoria.nombre}"? Los clientes y servicios que la tengan asignada la pierden, y el resto de sus datos no se toca.`,
      )
    ) {
      return;
    }
    await eliminarCategoria(categoria.id);
    await recargar();
  }

  const columnas: readonly Columna<Categoria>[] = [
    {
      clave: "nombre",
      titulo: "Nombre",
      celda: (fila) => <span className="mae-nombre">{fila.nombre}</span>,
    },
    {
      clave: "ambito",
      titulo: "Se aplica a",
      celda: (fila) => <span className="mae-dato">{ETIQUETAS_DE_AMBITO[fila.aplica_a]}</span>,
    },
    {
      clave: "acciones",
      titulo: "Acciones",
      alDerecha: true,
      celda: (fila) =>
        puedeEditar ? (
          <span className="tabla__acciones">
            <button
              type="button"
              className="mae-accion"
              onClick={() => setEdicion({ categoria: fila })}
            >
              Editar
            </button>
            <button
              type="button"
              className="mae-accion mae-accion--baja"
              onClick={() => void eliminar(fila)}
            >
              Eliminar
            </button>
          </span>
        ) : null,
    },
  ];

  return (
    <>
      <header className="mae-encabezado">
        <div>
          <p className="mae-encabezado__eyebrow">Datos maestros · Categorías</p>
          <h1>Categorías</h1>
          <p className="mae-encabezado__intro">
            Las etiquetas con las que organizás tu catálogo. Cada una decide si sirve para clientes,
            para servicios o para las dos cosas.
          </p>
        </div>
        {puedeEditar && (
          <div className="mae-encabezado__acciones">
            <Button onClick={() => setEdicion({ categoria: undefined })}>
              <span className="mae-cta__icono" aria-hidden="true">
                <IconoDeMas />
              </span>
              Nueva categoría
            </Button>
          </div>
        )}
      </header>

      <div className="mae-filtros">
        <Select
          id="dm-ambito"
          etiqueta="Filtrar por ámbito"
          opciones={[{ valor: "", etiqueta: "Todos los ámbitos" }, ...AMBITOS]}
          value={ambito}
          onChange={(evento) => {
            setAmbito(evento.target.value);
            void recargar(evento.target.value);
          }}
        />
      </div>

      <div className="mae-barra">
        <p className="mae-barra__cuenta">
          <b>{cuantas}</b> {cuantas === 1 ? "categoría" : "categorías"} en el catálogo
        </p>
      </div>

      <div className="mae-panel">
        <Tabla
          titulo={`${cuantas} categoria${cuantas === 1 ? "" : "s"}`}
          columnas={columnas}
          filas={listado.categorias}
          claveDeFila={(fila) => fila.id}
          vacia="Todavía no creaste ninguna categoría."
        />
      </div>

      <Modal
        abierto={edicion !== null}
        titulo={edicion?.categoria === undefined ? "Nueva categoría" : "Editar categoría"}
        onCerrar={() => setEdicion(null)}
      >
        {edicion !== null && (
          <FormularioDeCategoria
            {...(edicion.categoria !== undefined ? { categoria: edicion.categoria } : {})}
            onGuardar={guardar}
            onCancelar={() => setEdicion(null)}
            error={error}
          />
        )}
      </Modal>
    </>
  );
}
