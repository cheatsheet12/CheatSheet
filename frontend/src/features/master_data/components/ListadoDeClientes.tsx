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
import { SelectorDeCategorias } from "./SelectorDeCategorias";

const ORIGENES: readonly { valor: string; etiqueta: string }[] = [
  { valor: "", etiqueta: "Todos los origenes" },
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

  async function alternarEstado(cliente: Cliente): Promise<void> {
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
    { clave: "nombre", titulo: "Nombre", celda: (fila) => fila.nombre },
    { clave: "cuit", titulo: "CUIT", celda: (fila) => fila.cuit ?? "—" },
    { clave: "origen", titulo: "Origen", celda: (fila) => fila.origen },
    { clave: "whatsapp", titulo: "WhatsApp", celda: (fila) => fila.contacto_whatsapp ?? "—" },
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
          <>
            <Button variante="secundario" onClick={() => void abrirEdicion(fila)}>
              Editar
            </Button>{" "}
            <Button
              variante={fila.activo ? "destructivo" : "secundario"}
              {...(fila.activo
                ? { confirmacion: `Desactivar a ${fila.nombre}? Deja de estar en el catalogo.` }
                : {})}
              onClick={() => void alternarEstado(fila)}
            >
              {fila.activo ? "Desactivar" : "Reactivar"}
            </Button>
          </>
        ) : null,
    },
  ];

  return (
    <>
      <div className="dm-filtros">
        <Campo
          id="dm-buscador"
          etiqueta="Buscar"
          value={texto}
          onChange={(evento) => {
            setTexto(evento.target.value);
            void recargar({ texto: evento.target.value });
          }}
          ayuda="Por nombre o por CUIT."
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
          etiqueta="Categoria"
          opciones={[
            { valor: "", etiqueta: "Todas las categorias" },
            ...categoriasDisponibles.map((c) => ({ valor: c.id, etiqueta: c.nombre })),
          ]}
          value={categoria}
          onChange={(evento) => {
            setCategoria(evento.target.value);
            void recargar({ categoriaId: evento.target.value });
          }}
        />
        <label className="dm-filtros__casilla" htmlFor="dm-solo-activos">
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
        {puedeEditar && (
          <Button onClick={() => setEdicion({ cliente: undefined })}>Nuevo cliente</Button>
        )}
      </div>

      <Tabla
        titulo={`${listado.total} cliente${listado.total === 1 ? "" : "s"}`}
        columnas={columnas}
        filas={listado.clientes}
        claveDeFila={(fila) => fila.id}
        vacia="Todavia no hay clientes en el catalogo."
      />

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
          // Sólo al editar: una asignación necesita un elemento que ya tenga id.
          <SelectorDeCategorias
            ambito="CLIENTE"
            asignadas={asignadas}
            onAlternar={alternarCategoria}
          />
        )}
      </Modal>
    </>
  );
}
