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
 * **Las acciones de fila son iconos, y la baja está en el menú ⋯.** Facturar, Cobrar y Agendar se
 * usan todos los días y van como botones de icono; Editar y Desactivar, dentro de «más acciones».
 * Diez filas con un botón rojo cada una convierten el rojo en decoración justo donde tendría que
 * ser una advertencia; la advertencia la da la confirmación, que sigue siendo un diálogo y dice
 * qué pasa si se sigue adelante.
 */

"use client";

import { useEffect, useState } from "react";

import { Badge, Modal, Tabla } from "@/shared";
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
import { AccionesDeCliente, AvatarDeCliente } from "./FilaDeCliente";
import { HerramientasDeClientes } from "./HerramientasDeClientes";
import { IconoDeMas } from "./iconos";
import { SelectorDeCategorias } from "./SelectorDeCategorias";
import { VacioDeClientes } from "./VacioDeClientes";

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

  /** Vuelve al catálogo entero: los cuatro filtros a su valor de origen, y una sola recarga. */
  function limpiarFiltros(): void {
    setTexto("");
    setOrigen("");
    setCategoria("");
    setSoloActivos(false);
    void recargar({ texto: "", origen: "", categoriaId: "", soloActivos: false });
  }

  const hayFiltros = texto !== "" || origen !== "" || categoria !== "" || soloActivos;

  const columnas: readonly Columna<Cliente>[] = [
    {
      clave: "nombre",
      titulo: "Nombre",
      celda: (fila) => (
        <span className="mae-persona">
          <AvatarDeCliente nombre={fila.nombre} />
          <span className="mae-nombre">{fila.nombre}</span>
        </span>
      ),
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
          <AccionesDeCliente
            cliente={fila}
            onEditar={(cliente) => void abrirEdicion(cliente)}
            onAlternarEstado={(cliente) => void alternarEstado(cliente)}
          />
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
            <button
              type="button"
              className="mae-cta"
              onClick={() => setEdicion({ cliente: undefined })}
            >
              <span className="mae-cta__icono" aria-hidden="true">
                <IconoDeMas />
              </span>
              Nuevo cliente
            </button>
          </div>
        )}
      </header>

      <HerramientasDeClientes
        texto={texto}
        origen={origen}
        categoria={categoria}
        soloActivos={soloActivos}
        categorias={categoriasDisponibles}
        total={listado.total}
        onTexto={(valor) => {
          setTexto(valor);
          void recargar({ texto: valor });
        }}
        onOrigen={(valor) => {
          setOrigen(valor);
          void recargar({ origen: valor });
        }}
        onCategoria={(valor) => {
          setCategoria(valor);
          void recargar({ categoriaId: valor });
        }}
        onSoloActivos={(valor) => {
          setSoloActivos(valor);
          void recargar({ soloActivos: valor });
        }}
      />

      <div className="mae-panel mae-panel--clientes">
        {listado.clientes.length === 0 ? (
          <VacioDeClientes
            hayFiltros={hayFiltros}
            puedeEditar={puedeEditar}
            onNuevo={() => setEdicion({ cliente: undefined })}
            onLimpiar={limpiarFiltros}
          />
        ) : (
          <Tabla
            titulo="Listado de clientes"
            columnas={columnas}
            filas={listado.clientes}
            claveDeFila={(fila) => fila.id}
            vacia="Todavía no hay clientes en el catálogo."
          />
        )}
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
            categorias={
              edicion.cliente !== undefined ? (
                // Sólo al editar: una asignación necesita un elemento que ya tenga id.
                <SelectorDeCategorias
                  ambito="CLIENTE"
                  asignadas={asignadas}
                  onAlternar={alternarCategoria}
                />
              ) : undefined
            }
          />
        )}
      </Modal>
    </>
  );
}
