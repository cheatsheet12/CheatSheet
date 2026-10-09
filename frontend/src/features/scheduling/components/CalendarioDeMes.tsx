/**
 * La vista Mes de la agenda: la grilla clásica de lunes a domingo con los días del mes.
 *
 * Cada día muestra sus turnos como fichas chicas (hora y cliente) con el color de su estado; si
 * hay más de las que entran, un «+N más». Tocar un día lleva a la vista Día de esa fecha; tocar
 * una ficha abre el mismo detalle que las otras vistas. Los días de los meses vecinos que
 * completan las semanas se ven atenuados, y hoy lleva un aro.
 *
 * **No calcula nada de negocio.** Dibuja los turnos que la pantalla ya pidió para las semanas
 * visibles. En un celular las fichas se reemplazan por puntos de color (lo decide el CSS).
 */

"use client";

import Link from "next/link";
import type { MouseEvent } from "react";

import { ETIQUETAS_DE_ESTADO } from "../api/turno";
import type { Turno } from "../api/turno";
import { diaCorto, diaDe, diaLargo, horaEnAgenda, numeroDeDia, semanasDelMes } from "./calendario";
import type { NombresDeAgenda } from "./nombres";

export interface PropsDeCalendarioDeMes {
  /** Un día (`AAAA-MM-DD`) del mes que se mira. */
  readonly ancla: string;
  readonly hoy: string;
  readonly turnos: readonly Turno[];
  readonly nombres: NombresDeAgenda;
  /** Se llama con el día (`AAAA-MM-DD`) al que se quiere ir. */
  readonly onDia: (dia: string) => void;
}

/** Cuántas fichas entran en un día antes del «+N más». */
export const FICHAS_POR_DIA = 3;

/** Los turnos de cada día, ya ordenados por hora. */
function turnosPorDia(turnos: readonly Turno[]): ReadonlyMap<string, readonly Turno[]> {
  const mapa = new Map<string, Turno[]>();
  for (const turno of [...turnos].sort((a, b) => a.inicio.localeCompare(b.inicio))) {
    const dia = diaDe(turno.inicio);
    mapa.set(dia, [...(mapa.get(dia) ?? []), turno]);
  }
  return mapa;
}

export function CalendarioDeMes({
  ancla,
  hoy,
  turnos,
  nombres,
  onDia,
}: PropsDeCalendarioDeMes): JSX.Element {
  const semanas = semanasDelMes(ancla);
  const delDia = turnosPorDia(turnos);
  const cabecera = semanas[0] ?? [];
  const mes = ancla.slice(0, 7);

  return (
    <div className="age-mes">
      <div className="age-mes__cabecera" aria-hidden="true">
        {cabecera.map((dia) => (
          <span key={dia} className="age-mes__semana">
            {diaCorto(dia)}
          </span>
        ))}
      </div>
      <div className="age-mes__grilla" role="grid" aria-label="Días del mes">
        {semanas.map((semana) => (
          <div key={semana[0]} className="age-mes__fila" role="row">
            {semana.map((dia) => (
              <CeldaDeDia
                key={dia}
                dia={dia}
                afuera={dia.slice(0, 7) !== mes}
                esHoy={dia === hoy}
                turnos={delDia.get(dia) ?? []}
                nombres={nombres}
                onDia={onDia}
              />
            ))}
          </div>
        ))}
      </div>
      <p className="age-mes__ayuda">Tocá un día para ver su agenda completa.</p>
    </div>
  );
}

function etiquetaDelNumero(dia: string, cantidad: number): string {
  if (cantidad === 0) {
    return `Ver ${diaLargo(dia)}`;
  }
  return `Ver ${diaLargo(dia)}, ${cantidad} ${cantidad === 1 ? "turno" : "turnos"}`;
}

function CeldaDeDia({
  dia,
  afuera,
  esHoy,
  turnos,
  nombres,
  onDia,
}: {
  readonly dia: string;
  readonly afuera: boolean;
  readonly esHoy: boolean;
  readonly turnos: readonly Turno[];
  readonly nombres: NombresDeAgenda;
  readonly onDia: (dia: string) => void;
}): JSX.Element {
  const visibles = turnos.slice(0, FICHAS_POR_DIA);
  const resto = turnos.length - visibles.length;

  // Un clic en el hueco de la celda abre el día; un clic en una ficha abre el turno.
  function alTocar(evento: MouseEvent<HTMLDivElement>): void {
    if (!(evento.target instanceof Element) || evento.target.closest("a, button") === null) {
      onDia(dia);
    }
  }

  return (
    <div
      className="age-mes__dia"
      role="gridcell"
      aria-label={diaLargo(dia)}
      data-afuera={afuera ? "true" : undefined}
      data-hoy={esHoy ? "true" : undefined}
      onClick={alTocar}
    >
      <div className="age-mes__encabezado">
        <button
          type="button"
          className="age-mes__numero"
          aria-label={etiquetaDelNumero(dia, turnos.length)}
          onClick={() => onDia(dia)}
        >
          {numeroDeDia(dia)}
        </button>
        {turnos.length > 0 && (
          <span className="age-mes__cuenta" aria-hidden="true">
            {turnos.length}
          </span>
        )}
      </div>
      <ul className="age-mes__fichas">
        {visibles.map((turno) => (
          <li key={turno.id}>
            <FichaDeTurno turno={turno} nombres={nombres} />
          </li>
        ))}
      </ul>
      {resto > 0 && (
        <button type="button" className="age-mes__mas" onClick={() => onDia(dia)}>
          +{resto} más
        </button>
      )}
      {turnos.length > 0 && (
        <span className="age-mes__puntos" aria-hidden="true">
          {turnos.slice(0, 4).map((turno) => (
            <span key={turno.id} className="age-mes__punto" data-estado={turno.estado} />
          ))}
        </span>
      )}
    </div>
  );
}

function FichaDeTurno({
  turno,
  nombres,
}: {
  readonly turno: Turno;
  readonly nombres: NombresDeAgenda;
}): JSX.Element {
  const cliente = nombres.cliente(turno.cliente_id);
  const servicio = nombres.servicio(turno.servicio_id);
  const inicio = horaEnAgenda(turno.inicio);
  return (
    <Link
      href={`/agenda/${turno.id}`}
      className="age-mes__ficha"
      data-estado={turno.estado}
      aria-label={`${inicio}, ${cliente}, ${servicio}, ${ETIQUETAS_DE_ESTADO[turno.estado]}`}
      title={`${inicio} · ${cliente} · ${servicio}`}
    >
      <span className="age-mes__ficha-hora">{inicio}</span>
      <span className="age-mes__ficha-nombre">{cliente}</span>
    </Link>
  );
}
