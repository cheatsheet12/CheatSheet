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
 * **Editar y Eliminar van en el menú ⋯** (`MenuDeAcciones`); sólo «Eliminar» lleva el rojo, en
 * la palabra y no en una caja por fila.
 */

"use client";

import { useState } from "react";

import { Modal, Select, Tabla } from "@/shared";
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
import { AccionesDeCategoria, AmbitoDeCategoriaPastilla } from "./FilaDeCategoria";
import { IconoDeCategoria, IconoDeCategorias, IconoDeMas } from "./iconos";
import { AzulejoDeIcono, BuscadorConLupa, VacioDeMaestros } from "./PiezasDeMaestros";

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
  const [texto, setTexto] = useState("");
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

  /** La búsqueda es local: son pocas categorías y la API no filtra por texto. */
  const visibles = listado.categorias.filter((c) =>
    c.nombre.toLowerCase().includes(texto.trim().toLowerCase()),
  );
  const cuantas = visibles.length;
  const hayFiltros = texto !== "" || ambito !== "";

  function limpiarFiltros(): void {
    setTexto("");
    setAmbito("");
    void recargar("");
  }

  const columnas: readonly Columna<Categoria>[] = [
    {
      clave: "nombre",
      titulo: "Nombre",
      celda: (fila) => (
        <span className="mae-persona">
          <AzulejoDeIcono nombre={fila.nombre}>
            <IconoDeCategoria />
          </AzulejoDeIcono>
          <span className="mae-nombre">{fila.nombre}</span>
        </span>
      ),
    },
    {
      clave: "ambito",
      titulo: "Se aplica a",
      celda: (fila) => <AmbitoDeCategoriaPastilla ambito={fila.aplica_a} />,
    },
    {
      clave: "acciones",
      titulo: "Acciones",
      alDerecha: true,
      celda: (fila) =>
        puedeEditar ? (
          <AccionesDeCategoria
            categoria={fila}
            onEditar={(categoria) => setEdicion({ categoria })}
            onEliminar={(categoria) => void eliminar(categoria)}
          />
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
            <button
              type="button"
              className="mae-cta"
              onClick={() => setEdicion({ categoria: undefined })}
            >
              <span className="mae-cta__icono" aria-hidden="true">
                <IconoDeMas />
              </span>
              Nueva categoría
            </button>
          </div>
        )}
      </header>

      <div className="mae-herramientas" role="search">
        <BuscadorConLupa
          id="dm-buscador-categorias"
          valor={texto}
          placeholder="Buscar por nombre"
          onCambio={setTexto}
        />
        <Select
          id="dm-ambito"
          etiqueta="Filtrar por ámbito"
          etiquetaOculta
          opciones={[{ valor: "", etiqueta: "Todos los ámbitos" }, ...AMBITOS]}
          value={ambito}
          onChange={(evento) => {
            setAmbito(evento.target.value);
            void recargar(evento.target.value);
          }}
        />
        <p className="mae-herramientas__cuenta" aria-live="polite">
          {`${cuantas} ${cuantas === 1 ? "categoría" : "categorías"}`}
        </p>
      </div>

      {/* Las filas entran escalonadas con las reglas de `mae-panel--clientes`: es la misma tabla. */}
      <div className="mae-panel mae-panel--clientes mae-panel--categorias">
        {cuantas === 0 ? (
          <VacioDeMaestros
            icono={<IconoDeCategorias />}
            hayFiltros={hayFiltros}
            puedeEditar={puedeEditar}
            titulo="Todavía no creaste ninguna categoría."
            texto="Creá la primera para clasificar tus clientes y servicios."
            tituloFiltrado="Ninguna categoría coincide"
            etiquetaDeNuevo="Nueva categoría"
            onNuevo={() => setEdicion({ categoria: undefined })}
            onLimpiar={limpiarFiltros}
          />
        ) : (
          <Tabla
            titulo="Listado de categorías"
            columnas={columnas}
            filas={visibles}
            claveDeFila={(fila) => fila.id}
            vacia="Todavía no creaste ninguna categoría."
          />
        )}
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
