/**
 * Un eslabón de la cadena de recordatorios de un cobro (PAN-COB-02, HU-E6-02 RN-01, U7).
 *
 * Seis situaciones, y la pantalla dice cuál para que nadie lea «Programado» cuando el mensaje se está
 * reintentando o ya se descartó:
 *
 * - **Programado**: ningún envío empezó. Punteado, sin fecha: la ausencia de fecha significa que no
 *   salió, y eso es distinto de que haya salido y no sepamos qué pasó.
 * - **Enviando**: un envío empezó y todavía no tiene resultado.
 * - **Reintentando**: falló por una causa transitoria y vuelve a probar en el próximo barrido.
 *   «Intento 2 de 3» es el que **viene** (el primero ya falló); lleva el último error.
 * - **Enviado / Entregado / Leído**: el estado que Meta informó.
 * - **Fallido**: con el motivo en castellano debajo (o el código crudo si no lo conocemos).
 * - **No enviado**: el cobro se pagó o cerró mientras esperaba; no es una falla.
 */

import { Badge, formatearFechaHora, formatearHora, motivoDeFalla } from "@/shared";

import { INTENTOS_MAXIMOS_DE_RECORDATORIO } from "../api/cobro";
import type { Recordatorio } from "../api/cobro";
import { ICONO_CHAT, ICONO_RELOJ, tonoDeEntrega } from "./presentacion";

const COBRO_CERRADO = "COBRO_CERRADO";

type Situacion = "programado" | "enviando" | "reintentando" | "no_enviado" | "con_estado";

function situacionDe(recordatorio: Recordatorio): Situacion {
  if (recordatorio.enviado_en !== null) {
    return "con_estado";
  }
  if (recordatorio.ultimo_error === COBRO_CERRADO) {
    return "no_enviado";
  }
  if (recordatorio.proximo_intento_en !== null) {
    return "reintentando";
  }
  return recordatorio.intentos > 0 ? "enviando" : "programado";
}

function etiquetaDe(situacion: Situacion, recordatorio: Recordatorio): string {
  switch (situacion) {
    case "reintentando":
      return "Reintentando";
    case "enviando":
      return "Enviando";
    case "no_enviado":
      return "No enviado";
    case "programado":
      return "Programado";
    case "con_estado":
      return recordatorio.estado_entrega ?? "Programado";
  }
}

function detalleDe(situacion: Situacion, recordatorio: Recordatorio): string {
  if (situacion === "reintentando") {
    const proximo = Math.min(recordatorio.intentos + 1, INTENTOS_MAXIMOS_DE_RECORDATORIO);
    return `Reintentando · intento ${proximo} de ${INTENTOS_MAXIMOS_DE_RECORDATORIO} · próximo ${formatearHora(recordatorio.proximo_intento_en)}`;
  }
  return `${formatearFechaHora(recordatorio.enviado_en)} · ${recordatorio.canal}`;
}

/** El motivo que se muestra debajo, o `null` si no hay nada que explicar. */
function motivoDe(situacion: Situacion, recordatorio: Recordatorio): string | null {
  const falla = situacion === "con_estado" && recordatorio.estado_entrega === "FALLIDO";
  if (falla || situacion === "no_enviado" || situacion === "reintentando") {
    return motivoDeFalla(recordatorio.ultimo_error);
  }
  return null;
}

export function HitoDeRecordatorio({
  recordatorio,
}: {
  readonly recordatorio: Recordatorio;
}): JSX.Element {
  const situacion = situacionDe(recordatorio);
  const sinSalir = recordatorio.enviado_en === null;
  const motivo = motivoDe(situacion, recordatorio);
  return (
    <li className={`cob-hito${sinSalir ? " cob-hito--programado" : ""}`}>
      <span className="cob-hito__icono" aria-hidden>
        {sinSalir ? ICONO_RELOJ : ICONO_CHAT}
      </span>
      <span className="cob-hito__cuerpo">
        <span className="cob-hito__titulo">Recordatorio {recordatorio.paso}</span>
        <span className="cob-hito__detalle">{detalleDe(situacion, recordatorio)}</span>
        {motivo !== null && <span className="cob-hito__motivo">{motivo}</span>}
      </span>
      <Badge estado={tonoDe(situacion, recordatorio)}>{etiquetaDe(situacion, recordatorio)}</Badge>
    </li>
  );
}

function tonoDe(
  situacion: Situacion,
  recordatorio: Recordatorio,
): "ok" | "atencion" | "pendiente" | "error" {
  if (situacion === "reintentando" || situacion === "enviando") {
    return "atencion";
  }
  if (situacion === "no_enviado") {
    return "pendiente";
  }
  return tonoDeEntrega(recordatorio.estado_entrega);
}
