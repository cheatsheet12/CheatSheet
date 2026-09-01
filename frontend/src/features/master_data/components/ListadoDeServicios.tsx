/**
 * PAN-DM-02 — the service catalogue.
 *
 * The five columns HU-E4-02's first acceptance criterion names — nombre, precio, IVA,
 * duración y estado — plus the actions. Same shape as PAN-DM-01, deliberately: the two
 * screens are the same catalogue with different fields, and making them look alike is
 * cheaper for whoever uses them than making each one clever.
 *
 * **The price is rendered, never computed.** It arrives as text and leaves as text; the
 * VAT column shows the rate beside it. What a customer ends up paying is a `Comprobante`,
 * and that is epic 5.
 */

"use client";

import { useEffect, useState } from "react";

import { Badge, Button, Campo, Modal, Select, Tabla } from "@/shared";
import type { Columna } from "@/shared";

import {
  ETIQUETAS_DE_ALICUOTA,
  ErrorDeServicio,
  cambiarEstadoDeServicio,
  crearServicio,
  editarServicio,
  listarServicios,
} from "../api/servicio";
import type { DatosDeServicio, ListadoDeServicios as Listado, Servicio } from "../api/servicio";
import { categoriasDeServicio, clasificarServicio, listarCategorias } from "../api/categoria";
import type { Categoria } from "../api/categoria";
import { FormularioDeServicio } from "./FormularioDeServicio";
import { SelectorDeCategorias } from "./SelectorDeCategorias";

const AGENDABLE: readonly { valor: string; etiqueta: string }[] = [
  { valor: "", etiqueta: "Agendables y no agendables" },
  { valor: "true", etiqueta: "Solo agendables" },
  { valor: "false", etiqueta: "Solo no agendables" },
];

export interface PropsDeListadoDeServicios {
  readonly inicial: Listado;
  /** Administrador and Operador write; Solo Lectura only looks (navigation map §5). */
  readonly puedeEditar: boolean;
}

type Edicion = { readonly servicio: Servicio | undefined } | null;

/** `""` is "no filter", which is not the same as `false`. */
function agendableDe(valor: string): boolean | null {
  return valor === "" ? null : valor === "true";
}

export function ListadoDeServicios({
  inicial,
  puedeEditar,
}: PropsDeListadoDeServicios): JSX.Element {
  const [listado, setListado] = useState<Listado>(inicial);
  const [texto, setTexto] = useState("");
  const [agendable, setAgendable] = useState("");
  const [soloActivos, setSoloActivos] = useState(false);
  const [edicion, setEdicion] = useState<Edicion>(null);
  const [error, setError] = useState<string | null>(null);
  const [categoria, setCategoria] = useState("");
  const [categoriasDisponibles, setCategoriasDisponibles] = useState<readonly Categoria[]>([]);
  const [asignadas, setAsignadas] = useState<readonly Categoria[]>([]);

  async function recargar(filtros?: {
    texto?: string;
    agendable?: string;
    soloActivos?: boolean;
    categoriaId?: string;
  }): Promise<void> {
    const actualizado = await listarServicios({
      texto: filtros?.texto ?? texto,
      agendable: agendableDe(filtros?.agendable ?? agendable),
      soloActivos: filtros?.soloActivos ?? soloActivos,
      categoriaId: filtros?.categoriaId ?? categoria,
    });
    setListado(actualizado);
  }

  useEffect(() => {
    let vigente = true;
    listarCategorias("SERVICIO")
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

  async function abrirEdicion(servicio: Servicio): Promise<void> {
    setEdicion({ servicio });
    setAsignadas([]);
    setAsignadas(await categoriasDeServicio(servicio.id));
  }

  async function alternarCategoria(categoriaId: string, asignar: boolean): Promise<void> {
    const servicio = edicion?.servicio;
    if (servicio === undefined) {
      return;
    }
    const resultado = await clasificarServicio(servicio.id, categoriaId, asignar);
    setAsignadas(resultado.categorias);
    await recargar();
  }

  async function guardar(datos: DatosDeServicio): Promise<void> {
    setError(null);
    try {
      const existente = edicion?.servicio;
      if (existente === undefined) {
        await crearServicio(datos);
      } else {
        await editarServicio(existente.id, datos);
      }
      setEdicion(null);
      await recargar();
    } catch (fallo) {
      // The backend's message is the story's own text — «El precio debe ser mayor a
      // cero.», «La duracion es obligatoria…» — so it is shown as it came.
      setError(
        fallo instanceof ErrorDeServicio ? fallo.message : "No se pudo guardar el servicio.",
      );
    }
  }

  async function alternarEstado(servicio: Servicio): Promise<void> {
    await cambiarEstadoDeServicio(servicio.id, !servicio.activo);
    await recargar();
  }

  const columnas: readonly Columna<Servicio>[] = [
    { clave: "nombre", titulo: "Nombre", celda: (fila) => fila.nombre },
    { clave: "precio", titulo: "Precio", celda: (fila) => `$ ${fila.precio}` },
    {
      clave: "iva",
      titulo: "IVA",
      celda: (fila) => ETIQUETAS_DE_ALICUOTA[fila.alicuota_iva],
    },
    {
      clave: "duracion",
      titulo: "Duracion",
      celda: (fila) =>
        fila.duracion_estandar_min !== null ? `${fila.duracion_estandar_min} min` : "—",
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
          <>
            <Button variante="secundario" onClick={() => void abrirEdicion(fila)}>
              Editar
            </Button>{" "}
            <Button
              variante={fila.activo ? "destructivo" : "secundario"}
              {...(fila.activo
                ? { confirmacion: `Desactivar ${fila.nombre}? Deja de estar en el catalogo.` }
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
          id="dm-buscador-servicios"
          etiqueta="Buscar"
          value={texto}
          onChange={(evento) => {
            setTexto(evento.target.value);
            void recargar({ texto: evento.target.value });
          }}
          ayuda="Por nombre."
        />
        <Select
          id="dm-agendable"
          etiqueta="Agendables"
          opciones={AGENDABLE}
          value={agendable}
          onChange={(evento) => {
            setAgendable(evento.target.value);
            void recargar({ agendable: evento.target.value });
          }}
        />
        <Select
          id="dm-categoria-servicios"
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
        <label className="dm-filtros__casilla" htmlFor="dm-servicios-activos">
          <input
            id="dm-servicios-activos"
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
          <Button onClick={() => setEdicion({ servicio: undefined })}>Nuevo servicio</Button>
        )}
      </div>

      <Tabla
        titulo={`${listado.total} servicio${listado.total === 1 ? "" : "s"}`}
        columnas={columnas}
        filas={listado.servicios}
        claveDeFila={(fila) => fila.id}
        vacia="Todavia no hay servicios en el catalogo."
      />

      <Modal
        abierto={edicion !== null}
        titulo={edicion?.servicio === undefined ? "Nuevo servicio" : "Editar servicio"}
        onCerrar={() => setEdicion(null)}
      >
        {edicion !== null && (
          <FormularioDeServicio
            {...(edicion.servicio !== undefined ? { servicio: edicion.servicio } : {})}
            onGuardar={guardar}
            onCancelar={() => setEdicion(null)}
            error={error}
          />
        )}
        {edicion?.servicio !== undefined && (
          <SelectorDeCategorias
            ambito="SERVICIO"
            asignadas={asignadas}
            onAlternar={alternarCategoria}
          />
        )}
      </Modal>
    </>
  );
}
