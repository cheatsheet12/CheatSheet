/**
 * PAN-DM-03 — Datos Maestros · Categorías (HU-E4-03).
 *
 * The smallest of the three master-data screens, and the only one with a delete. The
 * confirmation HU-E4-03's fourth acceptance criterion asks for comes from
 * `Button variante="destructivo"`, which already confirms — and the wording says what will
 * happen, because «eliminar» on its own does not tell anybody that their clients are about
 * to lose a label.
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
        fallo instanceof ErrorDeCategoria ? fallo.message : "No se pudo guardar la categoria.",
      );
    }
  }

  async function eliminar(categoria: Categoria): Promise<void> {
    await eliminarCategoria(categoria.id);
    await recargar();
  }

  const columnas: readonly Columna<Categoria>[] = [
    { clave: "nombre", titulo: "Nombre", celda: (fila) => fila.nombre },
    {
      clave: "ambito",
      titulo: "Se aplica a",
      celda: (fila) => ETIQUETAS_DE_AMBITO[fila.aplica_a],
    },
    {
      clave: "acciones",
      titulo: "Acciones",
      alDerecha: true,
      celda: (fila) =>
        puedeEditar ? (
          <>
            <Button variante="secundario" onClick={() => setEdicion({ categoria: fila })}>
              Editar
            </Button>{" "}
            <Button
              variante="destructivo"
              confirmacion={`Eliminar "${fila.nombre}"? Los clientes y servicios que la tengan asignada la pierden, y el resto de sus datos no se toca.`}
              onClick={() => void eliminar(fila)}
            >
              Eliminar
            </Button>
          </>
        ) : null,
    },
  ];

  return (
    <>
      <div className="dm-filtros">
        <Select
          id="dm-ambito"
          etiqueta="Filtrar por ambito"
          opciones={[{ valor: "", etiqueta: "Todos los ambitos" }, ...AMBITOS]}
          value={ambito}
          onChange={(evento) => {
            setAmbito(evento.target.value);
            void recargar(evento.target.value);
          }}
        />
        {puedeEditar && (
          <Button onClick={() => setEdicion({ categoria: undefined })}>Nueva categoria</Button>
        )}
      </div>

      <Tabla
        titulo={`${listado.categorias.length} categoria${listado.categorias.length === 1 ? "" : "s"}`}
        columnas={columnas}
        filas={listado.categorias}
        claveDeFila={(fila) => fila.id}
        vacia="Todavia no creaste ninguna categoria."
      />

      <Modal
        abierto={edicion !== null}
        titulo={edicion?.categoria === undefined ? "Nueva categoria" : "Editar categoria"}
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
