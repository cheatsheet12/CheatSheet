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
 * **Cada recurso se lee como una ficha, aunque por debajo siga siendo una tabla.** Lo que hay
 * que comparar entre recursos son columnas —¿cuál atiende el jueves?, ¿cuál presta este
 * servicio?—, y una grilla de tarjetas sueltas obliga a buscar el mismo dato en un lugar
 * distinto de cada una. La fila queda separada, con superficie y sombra propias (`.age-ficha`),
 * y adentro el horario y las excepciones son fichas de texto: se ve como una tarjeta y se
 * recorre como una tabla, que es lo que hace falta.
 *
 * **El encabezado vive acá** por lo mismo que en la agenda: «Agregar recurso» es parte del
 * encabezado y sólo lo ve el Administrador, que es un dato que este componente ya tiene.
 */

"use client";

import { useState } from "react";

import { Alert, Badge, Button, Campo, Card, Modal, Select, Tabla, formatearFecha } from "@/shared";
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
import { IconoDeMas, IconoDeRecurso } from "./iconos";

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

/** «Lun», «Mié». La semana entera no entra en una celda escrita con los nombres completos. */
function abreviado(dia: number): string {
  return DIAS[dia]?.slice(0, 3) ?? "—";
}

/**
 * Los días de un mismo horario, en una sola etiqueta.
 *
 * Un tramo corrido se dice como tramo —«Lun a Vie»—; los días sueltos se enumeran. Tres es
 * el piso para el rango: con dos, «Lun a Mar» ocupa lo mismo que «Lun, Mar» y se lee peor.
 */
function diasDe(dias: readonly number[]): string {
  const ordenados = [...dias].sort((uno, otro) => uno - otro);
  const primero = ordenados[0] ?? 0;
  const ultimo = ordenados[ordenados.length - 1] ?? 0;
  const corrido = ultimo - primero + 1 === ordenados.length;
  return corrido && ordenados.length >= 3
    ? `${abreviado(primero)} a ${abreviado(ultimo)}`
    : ordenados.map(abreviado).join(", ");
}

/**
 * El horario semanal resumido.
 *
 * Una ficha por franja son cinco veces la misma frase: con lunes a viernes de 09:00 a 18:00
 * la celda se partía en cuatro renglones y estiraba la fila entera a ~230 px de alto, dejando
 * «Excepciones», «Estado» y «Acciones» arriba con blanco debajo. Las franjas que comparten
 * horario se juntan en «Lun a Vie · 09:00 a 18:00», y el detalle aparece sólo donde los
 * horarios difieren de verdad, que es lo único que hay para leer.
 *
 * Un día solo se sigue diciendo entero —«Martes 09:00 a 18:00»—: abreviarlo cuando no hay
 * nada que comprimir sería pagar el costo del resumen sin el beneficio.
 */
function resumenSemanal(patrones: readonly Patron[]): readonly string[] {
  const porHorario = new Map<string, number[]>();
  for (const patron of patrones) {
    const horario = horarioDe(patron);
    const dias = porHorario.get(horario);
    if (dias === undefined) {
      porHorario.set(horario, [patron.dia_semana]);
    } else {
      dias.push(patron.dia_semana);
    }
  }
  return [...porHorario]
    .map(([horario, dias]) => ({ horario, dias, desde: Math.min(...dias) }))
    .sort((uno, otro) => uno.desde - otro.desde)
    .map(({ horario, dias }) =>
      dias.length === 1
        ? `${DIAS[dias[0] ?? 0] ?? "—"} ${horario}`
        : `${diasDe(dias)} · ${horario}`,
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

  const [creando, setCreando] = useState(false);
  const [nombre, setNombre] = useState("");
  const [tipo, setTipo] = useState<TipoRecurso>("PERSONA");

  const [editando, setEditando] = useState<Recurso | null>(null);
  const [patrones, setPatrones] = useState<readonly FilaDePatron[]>([]);
  const [asociados, setAsociados] = useState<readonly string[]>([]);

  const [fechaDeExcepcion, setFechaDeExcepcion] = useState("");

  const nombresDeServicio = new Map(servicios.map((uno) => [uno.id, uno.nombre]));
  const horarioInvertido = patrones.some((uno) => uno.hora_inicio >= uno.hora_fin);
  // Qué días quedan cubiertos por las franjas que se están editando. Es lo que pinta la tira
  // de siete días de la tarjeta: comprobar el horario leyendo cinco selects es donde alguien
  // deja el jueves afuera sin darse cuenta.
  const diasCubiertos = new Set(patrones.map((uno) => uno.dia_semana));

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
    {
      clave: "nombre",
      titulo: "Recurso",
      celda: (fila) => (
        <span className="age-ficha__quien">
          <span className="age-ficha__icono" aria-hidden="true">
            <IconoDeRecurso />
          </span>
          <span>
            <b className="age-ficha__nombre">{fila.nombre}</b>
            <span className="age-ficha__tipo">{ETIQUETAS_DE_TIPO[fila.tipo]}</span>
          </span>
        </span>
      ),
    },
    {
      clave: "servicios",
      titulo: "Servicios",
      celda: (fila) =>
        fila.servicios.length === 0 ? (
          // Un recurso sin servicios no admite ninguno, y decirlo evita que alguien se
          // pregunte por qué no puede reservar en él.
          <span className="age-nada">Sin servicios asociados</span>
        ) : (
          <span className="age-chips">
            {fila.servicios.map((uno) => (
              <span className="age-chip" key={uno}>
                {nombresDeServicio.get(uno) ?? uno}
              </span>
            ))}
          </span>
        ),
    },
    {
      clave: "horario",
      titulo: "Horario semanal",
      celda: (fila) =>
        fila.patrones.length === 0 ? (
          <span className="age-nada">Sin horario configurado</span>
        ) : (
          <span className="age-chips">
            {resumenSemanal(fila.patrones).map((tramo) => (
              <span className="age-chip age-chip--horario" key={tramo}>
                {tramo}
              </span>
            ))}
          </span>
        ),
    },
    {
      clave: "excepciones",
      titulo: "Excepciones",
      // La fecha va formateada acá y cruda en el editor: en el listado es información para
      // leer de reojo, y en el editor es la clave por la que se borra una excepción.
      celda: (fila) =>
        fila.excepciones.length === 0 ? (
          <span className="age-nada">Ninguna</span>
        ) : (
          <span className="age-chips">
            {fila.excepciones.map((una) => (
              <span className="age-chip age-chip--excepcion" key={una.fecha}>
                {formatearFecha(una.fecha)} · {ETIQUETAS_DE_EXCEPCION[una.tipo]}
              </span>
            ))}
          </span>
        ),
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
        // Acción de texto y no dos rectángulos con borde por fila: es el estándar del panel
        // —`.faq-accion`, `.plt-accion`— y acá la caja pesaba tanto que hubo que bajarle el
        // padding para que entrara, que es la señal de que no cabía.
        puedeEditar ? (
          <span className="tabla__acciones">
            <button type="button" className="age-accion" onClick={() => abrirEdicion(fila)}>
              Configurar
            </button>
            <button
              type="button"
              className="age-accion"
              onClick={() =>
                void correr(
                  () => cambiarEstadoDeRecurso(fila.id, !fila.activo),
                  "No se pudo cambiar el estado.",
                )
              }
            >
              {fila.activo ? "Desactivar" : "Activar"}
            </button>
          </span>
        ) : null,
    },
  ];

  return (
    <div className="age-pantalla">
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
            <Button onClick={() => setCreando(true)}>
              <span aria-hidden="true" className="age-cta__icono">
                <IconoDeMas />
              </span>
              Agregar recurso
            </Button>
          </div>
        )}
      </div>

      {error !== null && (
        <Alert tono="error" titulo="No se pudo completar">
          {error}
        </Alert>
      )}

      {listado.recursos.length === 0 ? (
        <p className="age-vacio">{MENSAJE_SIN_RECURSOS}</p>
      ) : (
        <div className="age-fichas">
          <Tabla
            titulo="Recursos reservables"
            columnas={columnas}
            filas={listado.recursos}
            claveDeFila={(fila) => fila.id}
            vacia={MENSAJE_SIN_RECURSOS}
          />
        </div>
      )}

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
              {/* Vista previa, no control: se pinta con lo que dicen las franjas de abajo,
                  y encender el jueves al agregar una franja es la comprobación que hoy hay
                  que hacer leyendo cinco selects. */}
              <ul className="age-semana">
                {DIAS.map((dia, indice) => (
                  <li
                    key={dia}
                    className={`age-dia${diasCubiertos.has(indice) ? " age-dia--atiende" : ""}`}
                  >
                    <span className="age-dia__nombre">{dia.slice(0, 3)}</span>
                    <span className="age-dia__horas">
                      {diasCubiertos.has(indice) ? "atiende" : "cerrado"}
                    </span>
                  </li>
                ))}
              </ul>

              {patrones.map((uno, indice) => (
                <div className="age-franja" key={uno.clave}>
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
              <div className="age-servicios">
                {servicios.map((servicio) => (
                  <label
                    key={servicio.id}
                    className={`age-servicio${
                      asociados.includes(servicio.id) ? " age-servicio--asociado" : ""
                    }`}
                  >
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
                    <span className="age-servicio__duracion">
                      {servicio.duracion_estandar_min} min
                    </span>
                  </label>
                ))}
              </div>
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
                  {
                    clave: "fecha",
                    titulo: "Fecha",
                    // Cruda y monoespaciada: es la clave por la que se borra, y la que hay
                    // que poder comparar carácter por carácter con lo que se cargó.
                    celda: (fila) => <span className="age-fecha-iso">{fila.fecha}</span>,
                  },
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
              <div className="age-excepcion">
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
    </div>
  );
}
