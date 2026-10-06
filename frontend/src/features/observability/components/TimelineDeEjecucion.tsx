/**
 * El timeline de PAN-LOG-02: los pasos internos de una operación, en orden, con el que falló
 * señalado en rojo.
 *
 * **Es una lista ordenada y no una tabla.** Lo que el prototipo dibuja —una línea vertical
 * con puntos— afirma que hay una secuencia, y una tabla afirma que hay filas comparables
 * entre sí. Acá lo que importa es el orden y dónde se cortó, no comparar el paso 2 con el 4.
 *
 * **El punto que falló es el único rojo.** Un timeline donde todo se ve igual obliga a leer
 * los cuatro pasos para encontrar el que importa, que es justo lo que esta pantalla existe
 * para evitar.
 */

import {
  ETIQUETAS_DE_MODULO,
  ETIQUETAS_DE_RESULTADO,
  type DetalleDeOperacion,
  type Operacion,
} from "../api/bitacora";
import { partirMomento } from "./MarcasDeOperacion";

export interface PropsDeTimeline {
  readonly pasos: readonly Operacion[];
  /** El id del paso que falló, tal como lo devuelve el backend. */
  readonly pasoConError: DetalleDeOperacion["paso_con_error"];
}

function fallo(paso: Operacion, pasoConError: string | null): boolean {
  // Dos fuentes que dicen lo mismo: el resultado de la fila y el puntero del detalle. Se
  // aceptan las dos porque una operación importada de un backend viejo trae sólo una.
  return paso.resultado === "error" || paso.id === pasoConError;
}

export function TimelineDeEjecucion({ pasos, pasoConError }: PropsDeTimeline): JSX.Element {
  return (
    <ol className="log-tl" aria-label="Pasos de la operación">
      {pasos.map((paso) => {
        const rojo = fallo(paso, pasoConError);
        const { hora } = partirMomento(paso.timestamp);
        return (
          <li key={paso.id} className={`log-tl__paso${rojo ? " log-tl__paso--fallo" : ""}`}>
            <span
              className={`log-tl__punto log-tl__punto--${rojo ? "error" : "ok"}`}
              aria-hidden="true"
            >
              {rojo ? "✕" : "✓"}
            </span>
            <span className="log-tl__cuerpo">
              <b>{paso.accion}</b>
              <span>
                {ETIQUETAS_DE_MODULO[paso.modulo] ?? paso.modulo} ·{" "}
                {ETIQUETAS_DE_RESULTADO[paso.resultado]}
              </span>
            </span>
            <time className="log-tl__hora" dateTime={paso.timestamp}>
              {hora}
            </time>
          </li>
        );
      })}
    </ol>
  );
}
