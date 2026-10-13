/**
 * PAN-AGE-03 — Agenda · Configuración de recursos (HU-E7-04, HU-E7-05).
 *
 * El listado con nombre, tipo, servicios y estado —el primer criterio— más las tres cosas que
 * se configuran sobre un recurso: su horario semanal, sus servicios y sus excepciones.
 *
 * **La acción es desactivar, no eliminar** (RN-03). Un recurso borrado dejaría los turnos que
 * se prestaron en él apuntando a algo que ya no existe, y la historia pide explícitamente que
 * los turnos reservados se mantengan.
 *
 * **El horario se reemplaza entero.** Es lo que hace que configurarlo sea una operación y no
 * una serie de parches con orden significativo.
 *
 * **Cada recurso es una tarjeta** (`TarjetaDeRecurso`) en una grilla de una a tres columnas, con
 * la semana dibujada en lugar de una pastilla de texto. La búsqueda y los chips de tipo y estado
 * filtran en el cliente sobre el listado que la página ya trajo: no piden nada nuevo.
 *
 * **El encabezado vive acá** por lo mismo que en la agenda: «Agregar recurso» es parte del
 * encabezado y sólo lo ve el Administrador, que es un dato que este componente ya tiene.
 */

"use client";

import { Building2, Plus } from "lucide-react";
import { useState } from "react";

import { Alert, Button, Campo, Modal, Select } from "@/shared";

import {
  ErrorDeRecurso,
  cambiarEstadoDeRecurso,
  listarRecursos,
  registrarRecurso,
} from "../api/recurso";
import type { ListadoDeRecursos, Recurso, ServicioAgendable, TipoRecurso } from "../api/recurso";
import { EditorDeRecurso } from "./EditorDeRecurso";
import { HerramientasDeRecursos } from "./HerramientasDeRecursos";
import type { FiltroDeEstado, FiltroDeTipo } from "./HerramientasDeRecursos";
import { TarjetaDeRecurso } from "./TarjetaDeRecurso";

export interface PropsDeRecursosReservables {
  readonly inicial: ListadoDeRecursos;
  readonly servicios: readonly ServicioAgendable[];
  /** Sólo el Administrador configura; el caso de uso lo refuerza. */
  readonly puedeEditar: boolean;
}

const TIPOS: readonly { valor: string; etiqueta: string }[] = [
  { valor: "PERSONA", etiqueta: "Persona" },
  { valor: "ESPACIO", etiqueta: "Espacio" },
  { valor: "EQUIPO", etiqueta: "Equipo" },
];

/** Mayúsculas y acentos no cuentan al buscar: «sillon» encuentra «Sillón 1». */
function normalizar(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(new RegExp("[\u0300-\u036f]", "g"), "")
    .toLowerCase()
    .trim();
}

function coincide(
  recurso: Recurso,
  texto: string,
  tipo: FiltroDeTipo,
  estado: FiltroDeEstado,
): boolean {
  if (tipo !== "" && recurso.tipo !== tipo) {
    return false;
  }
  if (estado === "activos" && !recurso.activo) {
    return false;
  }
  if (estado === "inactivos" && recurso.activo) {
    return false;
  }
  return texto === "" || normalizar(recurso.nombre).includes(texto);
}

function BotonDeAgregar({
  onClick,
  compacto = false,
}: {
  readonly onClick: () => void;
  readonly compacto?: boolean;
}): JSX.Element {
  return (
    <button
      type="button"
      className={`age-cta${compacto ? " age-cta--compacto" : ""}`}
      onClick={onClick}
    >
      <span aria-hidden="true" className="age-cta__icono">
        <Plus />
      </span>
      Agregar recurso
    </button>
  );
}

export function RecursosReservables({
  inicial,
  servicios,
  puedeEditar,
}: PropsDeRecursosReservables): JSX.Element {
  const [listado, setListado] = useState<ListadoDeRecursos>(inicial);
  const [error, setError] = useState<string | null>(null);
  const [trabajando, setTrabajando] = useState(false);

  const [texto, setTexto] = useState("");
  const [filtroDeTipo, setFiltroDeTipo] = useState<FiltroDeTipo>("");
  const [filtroDeEstado, setFiltroDeEstado] = useState<FiltroDeEstado>("");

  const [creando, setCreando] = useState(false);
  const [nombre, setNombre] = useState("");
  const [tipo, setTipo] = useState<TipoRecurso>("PERSONA");

  const [editando, setEditando] = useState<Recurso | null>(null);

  const nombresDeServicio = new Map(servicios.map((uno) => [uno.id, uno.nombre]));
  const buscado = normalizar(texto);
  const visibles = listado.recursos.filter((uno) =>
    coincide(uno, buscado, filtroDeTipo, filtroDeEstado),
  );

  async function correr(accion: () => Promise<unknown>, porDefecto: string): Promise<void> {
    setError(null);
    setTrabajando(true);
    try {
      await accion();
      setListado(await listarRecursos());
    } catch (fallo) {
      setError(fallo instanceof ErrorDeRecurso ? fallo.message : porDefecto);
    } finally {
      setTrabajando(false);
    }
  }

  // Con un diálogo abierto, el error se lee adentro y no en la página que queda detrás (#74).
  // Abrir o cerrar un diálogo borra el error anterior: no es de lo que se va a hacer ahora.
  const conDialogo = creando || editando !== null;

  function abrirCreacion(): void {
    setError(null);
    setCreando(true);
  }

  function cerrarCreacion(): void {
    setCreando(false);
    setError(null);
  }

  function abrirEditor(recurso: Recurso): void {
    setError(null);
    setEditando(recurso);
  }

  function cerrarEditor(): void {
    setEditando(null);
    setError(null);
  }

  function limpiarFiltros(): void {
    setTexto("");
    setFiltroDeTipo("");
    setFiltroDeEstado("");
  }

  return (
    <div className="age-pantalla age-recursos">
      <div className="age-encabezado">
        <div>
          <p className="age-encabezado__eyebrow">Operaciones · Agenda</p>
          <h1 className="age-encabezado__titulo">Recursos reservables</h1>
          <p className="age-encabezado__intro">
            Una persona, un espacio o un equipo, con el horario en el que atiende y los servicios
            que se prestan en él. Sin al menos uno activo no se pueden reservar turnos.
          </p>
        </div>
        {puedeEditar && (
          <div className="age-encabezado__acciones">
            <BotonDeAgregar onClick={abrirCreacion} />
          </div>
        )}
      </div>

      {error !== null && !conDialogo && (
        <Alert tono="error" titulo="No se pudo completar">
          {error}
        </Alert>
      )}

      {listado.recursos.length === 0 ? (
        <div className="age-vacio-recursos">
          <span className="age-vacio-recursos__icono" aria-hidden="true">
            <Building2 />
          </span>
          <p className="age-vacio-recursos__titulo">Todavía no hay recursos reservables</p>
          <p className="age-vacio-recursos__texto">
            Sin al menos un recurso activo no se pueden reservar turnos.
          </p>
          {puedeEditar && <BotonDeAgregar compacto onClick={abrirCreacion} />}
        </div>
      ) : (
        <>
          <HerramientasDeRecursos
            texto={texto}
            tipo={filtroDeTipo}
            estado={filtroDeEstado}
            total={visibles.length}
            onTexto={setTexto}
            onTipo={setFiltroDeTipo}
            onEstado={setFiltroDeEstado}
          />
          {visibles.length === 0 ? (
            <div className="age-vacio-recursos">
              <span className="age-vacio-recursos__icono" aria-hidden="true">
                <Building2 />
              </span>
              <p className="age-vacio-recursos__titulo">Ningún recurso coincide</p>
              <p className="age-vacio-recursos__texto">
                Probá con otra búsqueda o quitá algún filtro.
              </p>
              <button type="button" className="age-vacio-recursos__accion" onClick={limpiarFiltros}>
                Limpiar filtros
              </button>
            </div>
          ) : (
            <div className="age-grilla">
              {visibles.map((recurso, indice) => (
                <TarjetaDeRecurso
                  key={recurso.id}
                  recurso={recurso}
                  nombresDeServicio={nombresDeServicio}
                  puedeEditar={puedeEditar}
                  indice={indice}
                  onConfigurar={abrirEditor}
                  onAlternarEstado={(uno) =>
                    void correr(
                      () => cambiarEstadoDeRecurso(uno.id, !uno.activo),
                      "No se pudo cambiar el estado.",
                    )
                  }
                />
              ))}
            </div>
          )}
        </>
      )}

      <Modal abierto={creando} titulo="Agregar recurso" onCerrar={cerrarCreacion}>
        <form
          className="dm-formulario"
          onSubmit={(evento) => {
            evento.preventDefault();
            void correr(async () => {
              await registrarRecurso({ nombre, tipo, patrones: [], servicios: [] });
              setCreando(false);
              setNombre("");
            }, "No se pudo crear el recurso.");
          }}
        >
          {error !== null && (
            <Alert tono="error" titulo="No se pudo completar">
              {error}
            </Alert>
          )}
          <p className="dm-intro">
            El recurso nace activo y <strong>sin servicios asociados</strong>, así que todavía no
            acepta reservas. El horario y los servicios se configuran después.
          </p>
          <Campo
            id="recurso-nombre"
            etiqueta="Nombre"
            value={nombre}
            onChange={(evento) => setNombre(evento.target.value)}
          />
          <Select
            id="recurso-tipo"
            etiqueta="Tipo"
            opciones={TIPOS}
            value={tipo}
            onChange={(evento) => setTipo(evento.target.value as TipoRecurso)}
          />
          <div className="dm-formulario__acciones">
            <Button variante="secundario" onClick={cerrarCreacion}>
              Volver
            </Button>
            <Button type="submit" disabled={nombre.trim() === ""} cargando={trabajando}>
              Crear
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        abierto={editando !== null}
        titulo={editando === null ? "" : `Configurar ${editando.nombre}`}
        onCerrar={cerrarEditor}
      >
        {editando !== null && (
          <EditorDeRecurso
            key={editando.id}
            recurso={editando}
            servicios={servicios}
            trabajando={trabajando}
            error={error}
            onCorrer={correr}
            onActualizado={setEditando}
            onCerrar={cerrarEditor}
          />
        )}
      </Modal>
    </div>
  );
}
