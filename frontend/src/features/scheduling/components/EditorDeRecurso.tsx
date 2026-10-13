/**
 * El contenido del diálogo «Configurar <recurso>»: horario semanal, servicios y excepciones.
 *
 * Son tres operaciones independientes, cada una con su propio botón de guardado —el horario se
 * reemplaza entero, los servicios también, y una excepción se agrega o se quita sola—, así que el
 * pie fijo sólo cierra el diálogo: no hay un «Guardar todo» que prometa algo que el backend no
 * hace. El estado de lo que se edita vive acá; quien lo monta decide cuándo está abierto y pone
 * `key` con el id del recurso para que cada apertura arranque de cero.
 */

"use client";

import { CalendarX, Clock, Wrench } from "lucide-react";
import { useState } from "react";

import { Alert, Button, Campo, Card, Select, Tabla } from "@/shared";

import {
  DIAS,
  ETIQUETAS_DE_EXCEPCION,
  asociarServicios,
  configurarDisponibilidad,
  quitarExcepcion,
} from "../api/recurso";
import type { Patron, Recurso, ServicioAgendable } from "../api/recurso";
import { FormularioDeExcepcion } from "./FormularioDeExcepcion";
import { horarioDeExcepcion, nuevaFila } from "./recursosDatos";
import type { FilaDePatron } from "./recursosDatos";

const OPCIONES_DE_DIA = DIAS.map((nombre, indice) => ({
  valor: String(indice),
  etiqueta: nombre,
}));

function filasDe(recurso: Recurso): FilaDePatron[] {
  if (recurso.patrones.length === 0) {
    return [nuevaFila()];
  }
  return recurso.patrones.map((uno) => ({ ...uno, clave: crypto.randomUUID() }));
}

export interface PropsDeEditorDeRecurso {
  readonly recurso: Recurso;
  readonly servicios: readonly ServicioAgendable[];
  readonly trabajando: boolean;
  /**
   * El rechazo de la última operación, o `null`. Se muestra en el pie fijo y no arriba: el
   * diálogo es largo, y el pie es lo que se ve al apretar cualquiera de sus botones (#74).
   */
  readonly error: string | null;
  /** Corre una operación, refresca el listado y muestra el error si falla. */
  readonly onCorrer: (accion: () => Promise<unknown>, porDefecto: string) => Promise<void>;
  /** El recurso que devuelve el backend tras agregar o quitar una excepción. */
  readonly onActualizado: (recurso: Recurso) => void;
  readonly onCerrar: () => void;
}

export function EditorDeRecurso({
  recurso,
  servicios,
  trabajando,
  error,
  onCorrer,
  onActualizado,
  onCerrar,
}: PropsDeEditorDeRecurso): JSX.Element {
  const [patrones, setPatrones] = useState<readonly FilaDePatron[]>(() => filasDe(recurso));
  const [asociados, setAsociados] = useState<readonly string[]>(recurso.servicios);
  // Texto y no número: así se puede escribir un valor inválido y ver el rechazo del backend.
  const [intervalo, setIntervalo] = useState(String(recurso.intervalo_entre_turnos_min));

  const horarioInvertido = patrones.some((uno) => uno.hora_inicio >= uno.hora_fin);
  // Qué días quedan cubiertos por las franjas que se están editando. Es lo que pinta la tira de
  // siete días: comprobar el horario leyendo cinco selects es donde alguien deja el jueves
  // afuera sin darse cuenta.
  const diasCubiertos = new Set(patrones.map((uno) => uno.dia_semana));

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

  return (
    <div className="age-editor">
      <Card titulo="Horario semanal">
        <p className="age-editor__ayuda">
          <Clock aria-hidden="true" />
          Los días que tengan al menos una franja se marcan arriba. El horario se guarda entero.
        </p>
        {/* Vista previa, no control: se pinta con lo que dicen las franjas de abajo. */}
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
              onChange={(evento) => cambiar(uno.clave, "hora_inicio", `${evento.target.value}:00`)}
            />
            <Campo
              id={`patron-hasta-${uno.clave}`}
              etiqueta="Hasta"
              type="time"
              value={uno.hora_fin.slice(0, 5)}
              onChange={(evento) => cambiar(uno.clave, "hora_fin", `${evento.target.value}:00`)}
            />
            <Campo
              id={`patron-slot-${uno.clave}`}
              etiqueta="Duración del slot (min)"
              ayuda="Paso de la grilla de horarios. La duración del turno es la del servicio"
              mono
              value={String(uno.duracion_slot_min)}
              onChange={(evento) => cambiar(uno.clave, "duracion_slot_min", evento.target.value)}
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
          <Alert tono="error">{"La hora de inicio debe ser anterior a la hora de fin."}</Alert>
        )}

        <Campo
          id="recurso-intervalo"
          etiqueta="Intervalo entre turnos (min)"
          ayuda="Se agrega después de cada turno. Aplica a las reservas nuevas."
          type="number"
          mono
          min={0}
          max={480}
          value={intervalo}
          onChange={(evento) => setIntervalo(evento.target.value)}
        />

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
              void onCorrer(
                () =>
                  configurarDisponibilidad(
                    recurso.id,
                    patrones.map(({ clave: _clave, ...resto }) => resto),
                    Number.parseInt(intervalo, 10) || 0,
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
        <p className="age-editor__ayuda">
          <Wrench aria-hidden="true" />
          Sólo estos servicios pueden reservarse en este recurso. Sin ninguno, el recurso no acepta
          turnos.
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
              <span className="age-servicio__duracion">{servicio.duracion_estandar_min} min</span>
            </label>
          ))}
        </div>
        <div className="dm-formulario__acciones">
          <Button
            cargando={trabajando}
            onClick={() =>
              void onCorrer(
                () => asociarServicios(recurso.id, asociados),
                "No se pudieron guardar los servicios.",
              )
            }
          >
            Guardar servicios
          </Button>
        </div>
      </Card>

      <Card titulo="Excepciones">
        <p className="age-editor__ayuda">
          <CalendarX aria-hidden="true" />
          <span>
            Un feriado, unas vacaciones o una apertura fuera de horario. La excepción{" "}
            <strong>reemplaza</strong> al horario habitual de ese día, y hay una sola por fecha.
          </span>
        </p>
        <Tabla
          titulo=""
          columnas={[
            {
              clave: "fecha",
              titulo: "Fecha",
              // Cruda y monoespaciada: es la clave por la que se borra, y la que hay que poder
              // comparar carácter por carácter con lo que se cargó.
              celda: (fila) => <span className="age-fecha-iso">{fila.fecha}</span>,
            },
            {
              clave: "tipo",
              titulo: "Tipo",
              celda: (fila) => ETIQUETAS_DE_EXCEPCION[fila.tipo],
            },
            {
              clave: "horario",
              titulo: "Horario",
              // #165: el horario especial se ve con su franja; un día sin atención no tiene.
              celda: (fila) => horarioDeExcepcion(fila),
            },
            {
              clave: "acciones",
              titulo: "Acciones",
              alDerecha: true,
              celda: (fila) => (
                <Button
                  variante="secundario"
                  onClick={() =>
                    void onCorrer(async () => {
                      onActualizado(await quitarExcepcion(recurso.id, fila.fecha));
                    }, "No se pudo quitar la excepción.")
                  }
                >
                  Quitar
                </Button>
              ),
            },
          ]}
          filas={recurso.excepciones}
          claveDeFila={(fila) => fila.fecha}
          vacia="Este recurso no tiene excepciones configuradas."
        />
        <FormularioDeExcepcion
          recurso={recurso}
          trabajando={trabajando}
          onCorrer={onCorrer}
          onActualizado={onActualizado}
        />
      </Card>

      <div className="age-editor__pie">
        {error !== null && (
          <Alert tono="error" titulo="No se pudo completar">
            {error}
          </Alert>
        )}
        <div className="age-editor__pie-acciones">
          <Button variante="secundario" onClick={onCerrar}>
            Listo
          </Button>
        </div>
      </div>
    </div>
  );
}
