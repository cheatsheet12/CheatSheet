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
 */

"use client";

import { useState } from "react";

import { Alert, Badge, Button, Campo, Card, Modal, Select, Tabla } from "@/shared";
import type { Columna } from "@/shared";

import {
  DIAS,
  ETIQUETAS_DE_EXCEPCION,
  ETIQUETAS_DE_TIPO,
  ErrorDeRecurso,
  MENSAJE_SIN_RECURSOS,
  asociarServicios,
  cambiarEstadoDeRecurso,
  configurarDisponibilidad,
  horarioDe,
  listarRecursos,
  quitarExcepcion,
  registrarExcepcion,
  registrarRecurso,
} from "../api/recurso";
import type {
  ListadoDeRecursos,
  Patron,
  Recurso,
  ServicioAgendable,
  TipoRecurso,
} from "../api/recurso";

export interface PropsDeRecursosReservables {
  readonly inicial: ListadoDeRecursos;
  readonly servicios: readonly ServicioAgendable[];
  /** Sólo el Administrador configura; el caso de uso lo refuerza. */
  readonly puedeEditar: boolean;
}

interface FilaDePatron extends Patron {
  readonly clave: string;
}

const TIPOS: readonly { valor: string; etiqueta: string }[] = [
  { valor: "PERSONA", etiqueta: "Persona" },
  { valor: "ESPACIO", etiqueta: "Espacio" },
  { valor: "EQUIPO", etiqueta: "Equipo" },
];

const OPCIONES_DE_DIA = DIAS.map((nombre, indice) => ({
  valor: String(indice),
  etiqueta: nombre,
}));

function nuevaFila(dia = 0): FilaDePatron {
  return {
    clave: crypto.randomUUID(),
    dia_semana: dia,
    hora_inicio: "09:00:00",
    hora_fin: "18:00:00",
    duracion_slot_min: 30,
  };
}

function filasDe(recurso: Recurso | null): FilaDePatron[] {
  if (recurso === null || recurso.patrones.length === 0) {
    return [nuevaFila()];
  }
  return recurso.patrones.map((uno) => ({ ...uno, clave: crypto.randomUUID() }));
}

export function RecursosReservables({
  inicial,
  servicios,
  puedeEditar,
}: PropsDeRecursosReservables): JSX.Element {
  const [listado, setListado] = useState<ListadoDeRecursos>(inicial);
  const [error, setError] = useState<string | null>(null);
  const [trabajando, setTrabajando] = useState(false);

  const [creando, setCreando] = useState(false);
  const [nombre, setNombre] = useState("");
  const [tipo, setTipo] = useState<TipoRecurso>("PERSONA");

  const [editando, setEditando] = useState<Recurso | null>(null);
  const [patrones, setPatrones] = useState<readonly FilaDePatron[]>([]);
  const [asociados, setAsociados] = useState<readonly string[]>([]);

  const [fechaDeExcepcion, setFechaDeExcepcion] = useState("");

  const nombresDeServicio = new Map(servicios.map((uno) => [uno.id, uno.nombre]));
  const horarioInvertido = patrones.some((uno) => uno.hora_inicio >= uno.hora_fin);

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

  function abrirEdicion(recurso: Recurso): void {
    setEditando(recurso);
    setPatrones(filasDe(recurso));
    setAsociados(recurso.servicios);
    setFechaDeExcepcion("");
  }

  function cambiar(clave: string, campo: keyof Patron, valor: string): void {
    setPatrones((previos) =>
      previos.map((uno) =>
        uno.clave === clave
          ? {
              ...uno,
              [campo]:
                campo === "dia_semana" || campo === "duracion_slot_min"
                  ? Number.parseInt(valor, 10) || 0
                  : valor,
            }
          : uno,
      ),
    );
  }

  const columnas: readonly Columna<Recurso>[] = [
    { clave: "nombre", titulo: "Nombre", celda: (fila) => fila.nombre },
    { clave: "tipo", titulo: "Tipo", celda: (fila) => ETIQUETAS_DE_TIPO[fila.tipo] },
    {
      clave: "servicios",
      titulo: "Servicios",
      celda: (fila) =>
        fila.servicios.length === 0
          ? // Un recurso sin servicios no admite ninguno, y decirlo evita que alguien se
            // pregunte por qué no puede reservar en él.
            "Sin servicios asociados"
          : fila.servicios.map((uno) => nombresDeServicio.get(uno) ?? uno).join(", "),
    },
    {
      clave: "horario",
      titulo: "Horario",
      celda: (fila) =>
        fila.patrones.length === 0
          ? "Sin horario configurado"
          : fila.patrones.map((uno) => `${DIAS[uno.dia_semana]} ${horarioDe(uno)}`).join(" · "),
    },
    {
      clave: "estado",
      titulo: "Estado",
      celda: (fila) => (
        <Badge estado={fila.activo ? "ok" : "pendiente"}>
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
            <Button variante="secundario" onClick={() => abrirEdicion(fila)}>
              Configurar
            </Button>
            <Button
              variante="secundario"
              onClick={() =>
                void correr(
                  () => cambiarEstadoDeRecurso(fila.id, !fila.activo),
                  "No se pudo cambiar el estado.",
                )
              }
            >
              {fila.activo ? "Desactivar" : "Activar"}
            </Button>
          </>
        ) : null,
    },
  ];

  return (
    <>
      {error !== null && (
        <Alert tono="error" titulo="No se pudo completar">
          {error}
        </Alert>
      )}

      {puedeEditar && (
        <div className="fac-acciones">
          <Button onClick={() => setCreando(true)}>Agregar recurso</Button>
        </div>
      )}

      <Tabla
        titulo="Recursos reservables"
        columnas={columnas}
        filas={listado.recursos}
        claveDeFila={(fila) => fila.id}
        vacia={MENSAJE_SIN_RECURSOS}
      />

      <Modal abierto={creando} titulo="Agregar recurso" onCerrar={() => setCreando(false)}>
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
            <Button variante="secundario" onClick={() => setCreando(false)}>
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
        onCerrar={() => setEditando(null)}
      >
        {editando !== null && (
          <>
            <Card titulo="Horario semanal">
              {patrones.map((uno, indice) => (
                <div className="fac-item" key={uno.clave}>
                  <Select
                    id={`patron-dia-${uno.clave}`}
                    etiqueta={`Franja ${indice + 1}`}
                    opciones={OPCIONES_DE_DIA}
                    value={String(uno.dia_semana)}
                    onChange={(evento) => cambiar(uno.clave, "dia_semana", evento.target.value)}
                  />
                  <Campo
                    id={`patron-desde-${uno.clave}`}
                    etiqueta="Desde"
                    type="time"
                    value={uno.hora_inicio.slice(0, 5)}
                    onChange={(evento) =>
                      cambiar(uno.clave, "hora_inicio", `${evento.target.value}:00`)
                    }
                  />
                  <Campo
                    id={`patron-hasta-${uno.clave}`}
                    etiqueta="Hasta"
                    type="time"
                    value={uno.hora_fin.slice(0, 5)}
                    onChange={(evento) =>
                      cambiar(uno.clave, "hora_fin", `${evento.target.value}:00`)
                    }
                  />
                  <Campo
                    id={`patron-slot-${uno.clave}`}
                    etiqueta="Minutos por turno"
                    mono
                    value={String(uno.duracion_slot_min)}
                    onChange={(evento) =>
                      cambiar(uno.clave, "duracion_slot_min", evento.target.value)
                    }
                  />
                  <Button
                    variante="secundario"
                    disabled={patrones.length === 1}
                    onClick={() =>
                      setPatrones((previos) => previos.filter((otro) => otro.clave !== uno.clave))
                    }
                  >
                    Quitar
                  </Button>
                </div>
              ))}

              {horarioInvertido && (
                <Alert tono="error">
                  {"La hora de inicio debe ser anterior a la hora de fin."}
                </Alert>
              )}

              <div className="dm-formulario__acciones">
                <Button
                  variante="secundario"
                  onClick={() => setPatrones((previos) => [...previos, nuevaFila()])}
                >
                  Agregar franja
                </Button>
                <Button
                  disabled={horarioInvertido}
                  cargando={trabajando}
                  onClick={() =>
                    void correr(
                      () =>
                        configurarDisponibilidad(
                          editando.id,
                          patrones.map(({ clave: _clave, ...resto }) => resto),
                        ),
                      "No se pudo guardar el horario.",
                    )
                  }
                >
                  Guardar horario
                </Button>
              </div>
            </Card>

            <Card titulo="Servicios que se prestan acá">
              <p className="dm-intro">
                Sólo estos servicios pueden reservarse en este recurso. Sin ninguno, el recurso no
                acepta turnos.
              </p>
              {servicios.map((servicio) => (
                <label key={servicio.id} className="fac-item">
                  <input
                    type="checkbox"
                    checked={asociados.includes(servicio.id)}
                    onChange={() =>
                      setAsociados((previos) =>
                        previos.includes(servicio.id)
                          ? previos.filter((uno) => uno !== servicio.id)
                          : [...previos, servicio.id],
                      )
                    }
                  />
                  {servicio.nombre}
                </label>
              ))}
              <div className="dm-formulario__acciones">
                <Button
                  cargando={trabajando}
                  onClick={() =>
                    void correr(
                      () => asociarServicios(editando.id, asociados),
                      "No se pudieron guardar los servicios.",
                    )
                  }
                >
                  Guardar servicios
                </Button>
              </div>
            </Card>

            <Card titulo="Excepciones">
              <p className="dm-intro">
                Un feriado, unas vacaciones o una apertura fuera de horario. La excepción{" "}
                <strong>reemplaza</strong> al horario habitual de ese día, y hay una sola por fecha.
              </p>
              <Tabla
                titulo=""
                columnas={[
                  { clave: "fecha", titulo: "Fecha", celda: (fila) => fila.fecha },
                  {
                    clave: "tipo",
                    titulo: "Tipo",
                    celda: (fila) => ETIQUETAS_DE_EXCEPCION[fila.tipo],
                  },
                  {
                    clave: "acciones",
                    titulo: "Acciones",
                    alDerecha: true,
                    celda: (fila) => (
                      <Button
                        variante="secundario"
                        onClick={() =>
                          void correr(async () => {
                            const actualizado = await quitarExcepcion(editando.id, fila.fecha);
                            setEditando(actualizado);
                          }, "No se pudo quitar la excepción.")
                        }
                      >
                        Quitar
                      </Button>
                    ),
                  },
                ]}
                filas={editando.excepciones}
                claveDeFila={(fila) => fila.fecha}
                vacia="Este recurso no tiene excepciones configuradas."
              />
              <div className="fac-item">
                <Campo
                  id="excepcion-fecha"
                  etiqueta="Día sin atención"
                  type="date"
                  value={fechaDeExcepcion}
                  onChange={(evento) => setFechaDeExcepcion(evento.target.value)}
                />
                <Button
                  disabled={fechaDeExcepcion === ""}
                  cargando={trabajando}
                  onClick={() =>
                    void correr(async () => {
                      const actualizado = await registrarExcepcion(editando.id, {
                        fecha: fechaDeExcepcion,
                        tipo: "BLOQUEO",
                      });
                      setEditando(actualizado);
                      setFechaDeExcepcion("");
                    }, "No se pudo agregar la excepción.")
                  }
                >
                  Bloquear el día
                </Button>
              </div>
            </Card>
          </>
        )}
      </Modal>
    </>
  );
}
