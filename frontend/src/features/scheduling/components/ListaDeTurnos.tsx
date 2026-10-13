/**
 * La vista Lista de la agenda: los turnos agrupados por día, uno por tarjeta.
 *
 * Cada tarjeta es **un solo enlace** al detalle del turno. Es lo que alguien busca con el
 * teléfono en la oreja, y un enlace que ocupa toda la fila se acierta sin apuntar. No hay menú
 * de acciones porque hoy ninguna se hace desde el listado: confirmar, cancelar, reprogramar y
 * marcar asistencia viven en el detalle, con sus confirmaciones y su control por rol.
 */

"use client";

import Link from "next/link";
import type { CSSProperties } from "react";

import { Badge } from "@/shared";

import { ETIQUETAS_DE_ESTADO, tonoDeEstado } from "../api/turno";
import type { Turno } from "../api/turno";
import { agruparPorDia, duracionLegible, encabezadoDeDia, horaEnAgenda } from "./calendario";
import { IconoDeFlecha, IconoDeRecurso } from "./iconos";
import { AvatarDeTurno } from "./nombres";
import type { NombresDeAgenda } from "./nombres";

export interface PropsDeListaDeTurnos {
  readonly turnos: readonly Turno[];
  /** El día de hoy (`AAAA-MM-DD`), para escribir «Hoy» y «Mañana». */
  readonly hoy: string;
  readonly nombres: NombresDeAgenda;
}

/** Más allá de la fila doce nadie está mirando la entrada: se escalona sólo hasta ahí. */
const TOPE_DE_ESCALONADO = 12;

export function ListaDeTurnos({ turnos, hoy, nombres }: PropsDeListaDeTurnos): JSX.Element {
  const grupos = agruparPorDia(turnos);
  let orden = 0;

  return (
    <section className="age-agenda" aria-label="Turnos">
      {grupos.map((grupo) => (
        <div className="age-jornada" key={grupo.dia}>
          <h2 className="age-jornada__titulo" id={`age-jornada-${grupo.dia}`}>
            {encabezadoDeDia(grupo.dia, hoy)}
            <span className="age-jornada__cuenta">
              {grupo.turnos.length} {grupo.turnos.length === 1 ? "turno" : "turnos"}
            </span>
          </h2>
          <ul className="age-jornada__lista" aria-labelledby={`age-jornada-${grupo.dia}`}>
            {grupo.turnos.map((turno) => {
              const indice = Math.min(orden, TOPE_DE_ESCALONADO);
              orden += 1;
              return (
                <li
                  key={turno.id}
                  className="age-jornada__item"
                  style={{ "--age-i": indice } as CSSProperties}
                >
                  <FilaDeTurno turno={turno} nombres={nombres} />
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </section>
  );
}

function FilaDeTurno({
  turno,
  nombres,
}: {
  readonly turno: Turno;
  readonly nombres: NombresDeAgenda;
}): JSX.Element {
  const cliente = nombres.cliente(turno.cliente_id);
  return (
    <Link className="age-fila" href={`/agenda/${turno.id}`} data-estado={turno.estado}>
      <span className="age-fila__hora">
        <b>{horaEnAgenda(turno.inicio)}</b>
        <span>hasta {horaEnAgenda(turno.fin)}</span>
      </span>
      <span className="age-fila__persona">
        <AvatarDeTurno nombre={cliente} />
        <span className="age-fila__textos">
          <span className="age-fila__cliente">{cliente}</span>
          <span className="age-fila__servicio">{nombres.servicio(turno.servicio_id)}</span>
        </span>
      </span>
      <span className="age-fila__recurso">
        <span className="age-fila__recurso-ico" aria-hidden="true">
          <IconoDeRecurso />
        </span>
        {nombres.recurso(turno.recurso_id)}
      </span>
      <span className="age-fila__duracion">{duracionLegible(turno.duracion_min)}</span>
      <Badge estado={tonoDeEstado(turno.estado)}>{ETIQUETAS_DE_ESTADO[turno.estado]}</Badge>
      <span className="age-fila__flecha" aria-hidden="true">
        <IconoDeFlecha />
      </span>
    </Link>
  );
}
