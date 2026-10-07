/**
 * Las vistas Semana y Día de la agenda: una grilla de tiempo.
 *
 * Las columnas son los días de la semana o, en la vista Día, los recursos; las filas son las
 * horas. Cada turno es un bloque posicionado por su inicio y su duración, con el color de su
 * estado, y es un enlace al detalle. Los que se pisan dentro de una columna se reparten el ancho.
 *
 * **No calcula nada de negocio.** Dibuja los turnos que la pantalla ya pidió; el rango lo
 * decide quien llama. La zona es la de la agenda (ver `calendario.ts`).
 */

"use client";

import Link from "next/link";
import type { CSSProperties } from "react";

import { ETIQUETAS_DE_ESTADO } from "../api/turno";
import type { EstadoTurno, Turno } from "../api/turno";
import type { Recurso } from "../api/recurso";
import {
  diaCorto,
  diaDe,
  diaLargo,
  horaEnAgenda,
  horasVisibles,
  minutosDelDia,
  numeroDeDia,
  repartirEnCarriles,
  semanaDe,
} from "./calendario";
import type { Franja, VistaDeAgenda } from "./calendario";
import type { NombresDeAgenda } from "./nombres";

export interface PropsDeCalendario {
  readonly vista: Exclude<VistaDeAgenda, "lista">;
  /** Un día (`AAAA-MM-DD`) de la semana o el día que se mira. */
  readonly ancla: string;
  /** Hoy (`AAAA-MM-DD`) y el instante de «ahora», para resaltar el día y trazar la línea. */
  readonly hoy: string;
  readonly ahora: string;
  readonly turnos: readonly Turno[];
  readonly recursos: readonly Recurso[];
  readonly nombres: NombresDeAgenda;
}

/** Alto de una hora, en píxeles. La grilla entera mide `horas × ALTO_DE_HORA`. */
const ALTO_DE_HORA = 64;

/** Un turno corto muestra una sola línea: con dos, el texto se sale del bloque. */
const MINUTOS_PARA_DOS_LINEAS = 40;

interface Columna {
  readonly clave: string;
  readonly titulo: string;
  readonly subtitulo: string;
  readonly etiqueta: string;
  readonly esHoy: boolean;
  readonly turnos: readonly Turno[];
}

function columnasPorDia(ancla: string, hoy: string, turnos: readonly Turno[]): readonly Columna[] {
  return semanaDe(ancla).map((dia) => ({
    clave: dia,
    titulo: diaCorto(dia),
    subtitulo: numeroDeDia(dia),
    etiqueta: diaLargo(dia),
    esHoy: dia === hoy,
    turnos: turnos.filter((turno) => diaDe(turno.inicio) === dia),
  }));
}

/**
 * Los recursos del día: los que existen (activos) más los que aparecen en un turno aunque la
 * lista no los traiga, así un turno nunca queda sin columna.
 */
function columnasPorRecurso(
  ancla: string,
  hoy: string,
  turnos: readonly Turno[],
  recursos: readonly Recurso[],
  nombres: NombresDeAgenda,
): readonly Columna[] {
  const delDia = turnos.filter((turno) => diaDe(turno.inicio) === ancla);
  const ids = new Set<string>();
  for (const recurso of recursos) {
    if (recurso.activo) {
      ids.add(recurso.id);
    }
  }
  for (const turno of delDia) {
    ids.add(turno.recurso_id);
  }
  if (ids.size === 0) {
    return [
      {
        clave: "todos",
        titulo: "Turnos",
        subtitulo: "",
        etiqueta: diaLargo(ancla),
        esHoy: ancla === hoy,
        turnos: delDia,
      },
    ];
  }
  return [...ids].map((id) => ({
    clave: id,
    titulo: nombres.recurso(id),
    subtitulo: "",
    etiqueta: nombres.recurso(id),
    esHoy: ancla === hoy,
    turnos: delDia.filter((turno) => turno.recurso_id === id),
  }));
}

export function CalendarioDeTurnos({
  vista,
  ancla,
  hoy,
  ahora,
  turnos,
  recursos,
  nombres,
}: PropsDeCalendario): JSX.Element {
  const columnas =
    vista === "semana"
      ? columnasPorDia(ancla, hoy, turnos)
      : columnasPorRecurso(ancla, hoy, turnos, recursos, nombres);
  const { desde, hasta } = horasVisibles(turnos);
  const horas = Array.from({ length: hasta - desde }, (_, indice) => desde + indice);
  const alto = (hasta - desde) * ALTO_DE_HORA;
  const hayHoy = columnas.some((columna) => columna.esHoy);
  const minutosAhora = minutosDelDia(ahora);
  const ahoraVisible = hayHoy && minutosAhora >= desde * 60 && minutosAhora < hasta * 60;

  return (
    <div
      className="age-cal"
      data-vista={vista}
      style={{ "--age-columnas": columnas.length, "--age-alto": `${alto}px` } as CSSProperties}
    >
      <div className="age-cal__scroll">
        <div className="age-cal__cabecera">
          <span className="age-cal__esquina" aria-hidden="true" />
          {columnas.map((columna) => (
            <div
              key={columna.clave}
              className="age-cal__titulo"
              data-hoy={columna.esHoy ? "true" : undefined}
            >
              <span className="age-cal__titulo-dia">{columna.titulo}</span>
              {columna.subtitulo !== "" && (
                <span className="age-cal__titulo-numero">{columna.subtitulo}</span>
              )}
              {vista === "dia" && (
                <span className="age-cal__titulo-cuenta">
                  {columna.turnos.length} {columna.turnos.length === 1 ? "turno" : "turnos"}
                </span>
              )}
            </div>
          ))}
        </div>

        <div className="age-cal__cuerpo" style={{ height: alto }}>
          <div className="age-cal__horas" aria-hidden="true">
            {horas.map((hora) => (
              <span
                key={hora}
                className="age-cal__hora"
                style={{ top: (hora - desde) * ALTO_DE_HORA }}
              >
                {String(hora).padStart(2, "0")}:00
              </span>
            ))}
          </div>
          {columnas.map((columna) => (
            <div
              key={columna.clave}
              className="age-cal__columna"
              role="group"
              aria-label={columna.etiqueta}
              data-hoy={columna.esHoy ? "true" : undefined}
              style={
                {
                  backgroundSize: `100% ${ALTO_DE_HORA}px`,
                } as CSSProperties
              }
            >
              {repartirEnCarriles(columna.turnos).map((franja) => (
                <BloqueDeTurno
                  key={franja.turno.id}
                  franja={franja}
                  base={desde * 60}
                  total={(hasta - desde) * 60}
                  nombres={nombres}
                />
              ))}
              {ahoraVisible && columna.esHoy && (
                <span
                  className="age-cal__ahora"
                  data-testid="linea-de-ahora"
                  aria-hidden="true"
                  style={{
                    top: `${((minutosAhora - desde * 60) / ((hasta - desde) * 60)) * 100}%`,
                  }}
                />
              )}
            </div>
          ))}
        </div>
      </div>
      <Leyenda />
    </div>
  );
}

function BloqueDeTurno({
  franja,
  base,
  total,
  nombres,
}: {
  readonly franja: Franja;
  readonly base: number;
  readonly total: number;
  readonly nombres: NombresDeAgenda;
}): JSX.Element {
  const { turno } = franja;
  const cliente = nombres.cliente(turno.cliente_id);
  const servicio = nombres.servicio(turno.servicio_id);
  const inicio = horaEnAgenda(turno.inicio);
  const fin = horaEnAgenda(turno.fin);
  const corto = franja.fin - franja.inicio < MINUTOS_PARA_DOS_LINEAS;
  return (
    <Link
      href={`/agenda/${turno.id}`}
      className="age-bloque"
      data-estado={turno.estado}
      data-corto={corto ? "true" : undefined}
      aria-label={`${inicio} a ${fin}, ${cliente}, ${servicio}, ${ETIQUETAS_DE_ESTADO[turno.estado]}`}
      title={`${inicio}–${fin} · ${cliente} · ${servicio}`}
      style={{
        top: `${((franja.inicio - base) / total) * 100}%`,
        height: `${((franja.fin - franja.inicio) / total) * 100}%`,
        left: `${(franja.carril / franja.carriles) * 100}%`,
        width: `${100 / franja.carriles}%`,
      }}
    >
      <span className="age-bloque__hora">
        {inicio}–{fin}
      </span>
      <span className="age-bloque__cliente">{cliente}</span>
      {!corto && <span className="age-bloque__servicio">{servicio}</span>}
    </Link>
  );
}

const ESTADOS_DE_LA_LEYENDA: readonly EstadoTurno[] = [
  "RESERVADO",
  "CONFIRMADO",
  "COMPLETADO",
  "NO_SHOW",
  "CANCELADO",
];

function Leyenda(): JSX.Element {
  return (
    <ul className="age-cal__leyenda" aria-label="Colores por estado">
      {ESTADOS_DE_LA_LEYENDA.map((estado) => (
        <li key={estado} className="age-cal__leyenda-item" data-estado={estado}>
          <span className="age-cal__leyenda-punto" aria-hidden="true" />
          {ETIQUETAS_DE_ESTADO[estado]}
        </li>
      ))}
    </ul>
  );
}
