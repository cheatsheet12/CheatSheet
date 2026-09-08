/**
 * PAN-DM-01 — the customer catalogue.
 *
 * The five columns HU-E4-01's first acceptance criterion names — nombre, CUIT, origen,
 * WhatsApp y estado — plus the actions. The initial page is rendered by the server
 * component; this takes over so filtering and saving update the table in place.
 *
 * **`origen` is shown and never offered for editing** (RN-01). It is the column that says
 * whether a row came from the panel, from the company's spreadsheet or from the agent,
 * and it is what epic 4 will make interesting.
 *
 * **There is no delete action.** Deactivating is what the catalogue has instead, because
 * `comprobante`, `cobro` and `turno` reference a client by id and a removed row would
 * leave tax documents pointing at nothing.
 *
 * **El encabezado lo dibuja este componente y no `page.tsx`.** El CTA depende del rol y abre
 * el formulario, así que necesita estado; dejar el título en el server component y el botón
 * acá los separaba en dos bloques, y el botón terminaba metido en la fila de filtros —que es
 * donde estaba— sin pertenecer a nada. Es lo mismo que hacen PAN-FAC-01 y PAN-WA-02.
 *
 * **Las acciones de fila son texto, no botones con caja.** Diez filas con un botón de borde
 * rojo cada una convierten el rojo en decoración justo donde tendría que ser una advertencia.
 * La advertencia la da la confirmación, que sigue siendo un diálogo modal y dice qué pasa si
 * se sigue adelante.
 */

"use client";

import { useEffect, useState } from "react";

import { Badge, Button, Campo, Modal, Select, Tabla } from "@/shared";
import type { Columna } from "@/shared";

import {
  ErrorDeCatalogo,
  cambiarEstadoDeCliente,
  crearCliente,
  editarCliente,
  listarClientes,
} from "../api/cliente";
import type { Cliente, DatosDeCliente, ListadoDeClientes as Listado } from "../api/cliente";
import { categoriasDeCliente, clasificarCliente, listarCategorias } from "../api/categoria";
import type { Categoria } from "../api/categoria";
import { FormularioDeCliente } from "./FormularioDeCliente";
import { IconoDeMas } from "./iconos";
import { SelectorDeCategorias } from "./SelectorDeCategorias";

const ORIGENES: readonly { valor: string; etiqueta: string }[] = [
  { valor: "", etiqueta: "Todos los orígenes" },
  { valor: "PANEL", etiqueta: "Panel" },
  { valor: "PLANILLA", etiqueta: "Planilla" },
  { valor: "AGENTE", etiqueta: "Agente" },
];

export interface PropsDeListado {
  readonly inicial: Listado;
  /** Administrador and Operador write; Solo Lectura only looks (navigation map §5). */
  readonly puedeEditar: boolean;
}

/** What the form is doing right now. `null` means it is closed. */
type Edicion = { readonly cliente: Cliente | undefined } | null;

export function ListadoDeClientes({ inicial, puedeEditar }: PropsDeListado): JSX.Element {
  const [listado, setListado] = useState<Listado>(inicial);
  const [texto, setTexto] = useState("");
  const [origen, setOrigen] = useState("");
  const [soloActivos, setSoloActivos] = useState(false);
  const [edicion, setEdicion] = useState<Edicion>(null);
  const [error, setError] = useState<string | null>(null);
  const [duplicadoId, setDuplicadoId] = useState<string | null>(null);
  const [categoria, setCategoria] = useState("");
  const [categoriasDisponibles, setCategoriasDisponibles] = useState<readonly Categoria[]>([]);
  const [asignadas, setAsignadas] = useState<readonly Categoria[]>([]);

  async function recargar(filtros?: {
    texto?: string;
    origen?: string;
    soloActivos?: boolean;
    categoriaId?: string;
  }): Promise<void> {
    const actualizado = await listarClientes({
      texto: filtros?.texto ?? texto,
      origen: (filtros?.origen ?? origen) as "" | Cliente["origen"],
      soloActivos: filtros?.soloActivos ?? soloActivos,
      categoriaId: filtros?.categoriaId ?? categoria,
    });
    setListado(actualizado);
  }

  // El filtro por categoría de HU-E4-04. Se piden las de ámbito CLIENTE, que el backend
  // devuelve junto con las de AMBOS.
  useEffect(() => {
    let vigente = true;
    listarCategorias("CLIENTE")
      .then((listadoDeCategorias) => {
        if (vigente) {
          setCategoriasDisponibles(listadoDeCategorias.categorias);
        }
      })
      .catch(() => undefined);
    return () => {
      vigente = false;
    };
  }, []);

  /** Al abrir el formulario de edición, las que el cliente ya tiene. */
  async function abrirEdicion(cliente: Cliente): Promise<void> {
    setEdicion({ cliente });
    setAsignadas([]);
    const actuales = await categoriasDeCliente(cliente.id);
    setAsignadas(actuales);
  }

  async function alternarCategoria(categoriaId: string, asignar: boolean): Promise<void> {
    const cliente = edicion?.cliente;
    if (cliente === undefined) {
      return;
    }
    const resultado = await clasificarCliente(cliente.id, categoriaId, asignar);
    setAsignadas(resultado.categorias);
    await recargar();
  }

  async function guardar(datos: DatosDeCliente): Promise<void> {
    setError(null);
    setDuplicadoId(null);
    try {
      const existente = edicion?.cliente;
      if (existente === undefined) {
        await crearCliente(datos);
      } else {
        await editarCliente(existente.id, datos);
      }
      setEdicion(null);
      await recargar();
    } catch (fallo) {
      if (fallo instanceof ErrorDeCatalogo) {
        setError(fallo.message);
        setDuplicadoId(fallo.clienteExistenteId);
        return;
      }
      setError("No se pudo guardar el cliente.");
    }
  }

  /**
   * La baja pregunta antes de correr; la reactivación no, porque no hay nada que deshacer.
   *
   * La confirmación la disparaba `Button variante="destructivo"`, que además pintaba la
   * celda con un borde rojo. Acá la acción es texto y la pregunta se hace a mano: es el
   * mismo diálogo modal del navegador, con la misma frase, sin la caja roja en cada fila.
   */
  async function alternarEstado(cliente: Cliente): Promise<void> {
    if (
      cliente.activo &&
      !window.confirm(`¿Desactivar a ${cliente.nombre}? Deja de estar en el catálogo.`)
    ) {
      return;
    }
    await cambiarEstadoDeCliente(cliente.id, !cliente.activo);
    await recargar();
  }

  /** Closes the form and leaves the duplicate on screen, which is what «verlo» means here. */
  function verDuplicado(id: string): void {
    setEdicion(null);
    setError(null);
    setDuplicadoId(null);
    setTexto(id);
    void listarClientes().then((todos) =>
      setListado({
        clientes: todos.clientes.filter((c) => c.id === id),
        total: todos.clientes.filter((c) => c.id === id).length,
      }),
    );
  }

  const columnas: readonly Columna<Cliente>[] = [
    {
      clave: "nombre",
      titulo: "Nombre",
      celda: (fila) => <span className="mae-nombre">{fila.nombre}</span>,
    },
    {
      clave: "cuit",
      titulo: "CUIT",
      // El guion largo va sin envoltorio propio de estilo distinto al del dato ausente: es
      // «acá no hay nada», y en tinta plena competiría con los CUIT que sí están.
      celda: (fila) =>
        fila.cuit === null ? (
          <span className="mae-dato mae-dato--tenue">—</span>
        ) : (
          <span className="mae-mono">{fila.cuit}</span>
        ),
    },
    {
      clave: "origen",
      titulo: "Origen",
      celda: (fila) => <span className="mae-origen">{fila.origen}</span>,
    },
    {
      clave: "whatsapp",
      titulo: "WhatsApp",
      celda: (fila) =>
        fila.contacto_whatsapp === null ? (
          <span className="mae-dato mae-dato--tenue">—</span>
        ) : (
          <span className="mae-mono">{fila.contacto_whatsapp}</span>
        ),
    },
    {
      clave: "estado",
      titulo: "Estado",
      celda: (fila) => (
        <Badge estado={fila.activo ? "ok" : "atencion"}>
          {fila.activo ? "Activo" : "Inactivo"}
        </Badge>
      ),
    },
    {
      clave: "acciones",
      titulo: "Acciones",
      alDerecha: true,
      celda: (fila) =>
        puedeEditar ? (
          <span className="tabla__acciones">
            <button type="button" className="mae-accion" onClick={() => void abrirEdicion(fila)}>
              Editar
            </button>
            <button
              type="button"
              className={`mae-accion${fila.activo ? " mae-accion--baja" : ""}`}
              onClick={() => void alternarEstado(fila)}
            >
              {fila.activo ? "Desactivar" : "Reactivar"}
            </button>
          </span>
        ) : null,
    },
  ];

  return (
    <>
      <header className="mae-encabezado">
        <div>
          <p className="mae-encabezado__eyebrow">Datos maestros · Clientes</p>
          <h1>Clientes</h1>
          <p className="mae-encabezado__intro">
            El catálogo de clientes de tu empresa. Lo que creés acá queda disponible para
            facturación, cobros y agenda.
          </p>
        </div>
        {puedeEditar && (
          <div className="mae-encabezado__acciones">
            <Button onClick={() => setEdicion({ cliente: undefined })}>
              <span className="mae-cta__icono" aria-hidden="true">
                <IconoDeMas />
              </span>
              Nuevo cliente
            </Button>
          </div>
        )}
      </header>

      <div className="mae-filtros">
        <Campo
          id="dm-buscador"
          etiqueta="Buscar"
          value={texto}
          onChange={(evento) => {
            setTexto(evento.target.value);
            void recargar({ texto: evento.target.value });
          }}
          placeholder="Nombre o CUIT"
        />
        <Select
          id="dm-origen"
          etiqueta="Origen"
          opciones={ORIGENES}
          value={origen}
          onChange={(evento) => {
            setOrigen(evento.target.value);
            void recargar({ origen: evento.target.value });
          }}
        />
        <Select
          id="dm-categoria"
          etiqueta="Categoría"
          opciones={[
            { valor: "", etiqueta: "Todas las categorías" },
            ...categoriasDisponibles.map((c) => ({ valor: c.id, etiqueta: c.nombre })),
          ]}
          value={categoria}
          onChange={(evento) => {
            setCategoria(evento.target.value);
            void recargar({ categoriaId: evento.target.value });
          }}
        />
        <label className="mae-casilla" htmlFor="dm-solo-activos">
          <input
            id="dm-solo-activos"
            type="checkbox"
            checked={soloActivos}
            onChange={(evento) => {
              setSoloActivos(evento.target.checked);
              void recargar({ soloActivos: evento.target.checked });
            }}
          />
          Solo activos
        </label>
      </div>

      <div className="mae-barra">
        <p className="mae-barra__cuenta">
          <b>{listado.total}</b> {listado.total === 1 ? "cliente" : "clientes"} en el catálogo
        </p>
      </div>

      <div className="mae-panel">
        <Tabla
          titulo={`${listado.total} cliente${listado.total === 1 ? "" : "s"}`}
          columnas={columnas}
          filas={listado.clientes}
          claveDeFila={(fila) => fila.id}
          vacia="Todavía no hay clientes en el catálogo."
        />
      </div>

      <Modal
        abierto={edicion !== null}
        titulo={edicion?.cliente === undefined ? "Nuevo cliente" : "Editar cliente"}
        onCerrar={() => setEdicion(null)}
      >
        {edicion !== null && (
          <FormularioDeCliente
            {...(edicion.cliente !== undefined ? { cliente: edicion.cliente } : {})}
            onGuardar={guardar}
            onCancelar={() => setEdicion(null)}
            error={error}
            duplicadoId={duplicadoId}
            onVerDuplicado={verDuplicado}
          />
        )}
        {edicion?.cliente !== undefined && (
          // Sólo al editar: una asignación necesita un elemento que ya tenga id. La línea
          // separa lo que el cliente **es** de cómo está etiquetado; sin ella los dos bloques
          // se leen como un único formulario largo.
          <>
            <hr className="mae-form__separador" />
            <SelectorDeCategorias
              ambito="CLIENTE"
              asignadas={asignadas}
              onAlternar={alternarCategoria}
            />
          </>
        )}
      </Modal>
    </>
  );
}
