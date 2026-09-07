/**
 * PAN-AGE-01 — Agenda · Vista de turnos (HU-E7-01).
 *
 * Por recurso y por rango de fechas, con el día en curso por defecto (RN-01). El rango lo
 * decide el backend cuando no se manda ninguno, así que esta pantalla arranca sin filtros y
 * los agrega cuando alguien los toca — un `desde`/`hasta` puesto acá con la fecha del
 * navegador podría no coincidir con el día que el local está atendiendo.
 *
 * **«Reprogramado» no aparece en ningún lado**, y es a propósito (RN-02): un turno movido se ve
 * en su franja nueva con el estado que tenía. Que se movió lo dice la bitácora.
 */

"use client";

import Link from "next/link";
import { useState } from "react";

import { Alert, Badge, Campo, Select, Tabla, formatearFecha } from "@/shared";
import type { Columna } from "@/shared";

import {
  ETIQUETAS_DE_ESTADO,
  ErrorDeTurno,
  MENSAJE_SIN_TURNOS,
  horaDe,
  listarTurnos,
  tonoDeEstado,
} from "../api/turno";
import type { FiltrosDeAgenda, ListadoDeTurnos, Turno } from "../api/turno";
import type { Recurso } from "../api/recurso";

export interface PropsDeAgendaDelDia {
  readonly inicial: ListadoDeTurnos;
  readonly recursos: readonly Recurso[];
  /** Administrador y Operador reservan; Solo Lectura sólo mira (HU-E7-01 RN-03). */
  readonly puedeGestionar: boolean;
}

/**
 * Los cinco estados del enum, con la etiqueta que la historia les da.
 *
 * El valor que viaja es el del dominio: mandar «No se presentó» al backend obligaría a
 * traducir del otro lado, que es el seam donde una traducción mal hecha devuelve la lista
 * entera.
 */
const ESTADOS: readonly { valor: string; etiqueta: string }[] = [
  { valor: "", etiqueta: "Todos los estados" },
  { valor: "RESERVADO", etiqueta: "Reservado" },
  { valor: "CONFIRMADO", etiqueta: "Confirmado" },
  { valor: "COMPLETADO", etiqueta: "Completado" },
  { valor: "NO_SHOW", etiqueta: "No se presentó" },
  { valor: "CANCELADO", etiqueta: "Cancelado" },
];

export function AgendaDelDia({
  inicial,
  recursos,
  puedeGestionar,
}: PropsDeAgendaDelDia): JSX.Element {
  const [listado, setListado] = useState<ListadoDeTurnos>(inicial);
  const [filtros, setFiltros] = useState<FiltrosDeAgenda>({});
  const [error, setError] = useState<string | null>(null);

  const nombres = new Map(recursos.map((uno) => [uno.id, uno.nombre]));

  async function aplicar(cambios: FiltrosDeAgenda): Promise<void> {
    const siguientes = { ...filtros, ...cambios };
    setFiltros(siguientes);
    setError(null);
    try {
      setListado(await listarTurnos(siguientes));
    } catch (fallo) {
      setError(fallo instanceof ErrorDeTurno ? fallo.message : "No se pudo actualizar la agenda.");
    }
  }

  const columnas: readonly Columna<Turno>[] = [
    {
      clave: "hora",
      titulo: "Hora",
      celda: (fila) => (
        <Link href={`/agenda/${fila.id}`}>
          {horaDe(fila.inicio)} a {horaDe(fila.fin)}
        </Link>
      ),
    },
    { clave: "fecha", titulo: "Fecha", celda: (fila) => formatearFecha(fila.inicio) },
    {
      clave: "recurso",
      titulo: "Recurso",
      // El nombre y no el id: un id en una agenda no le dice nada a quien la mira. Si el
      // recurso no está en la lista —porque se desactivó y el filtro pide sólo activos—, el
      // id es mejor que una celda vacía.
      celda: (fila) => nombres.get(fila.recurso_id) ?? fila.recurso_id,
    },
    {
      clave: "estado",
      titulo: "Estado",
      celda: (fila) => (
        <Badge estado={tonoDeEstado(fila.estado)}>{ETIQUETAS_DE_ESTADO[fila.estado]}</Badge>
      ),
    },
  ];

  return (
    <>
      {error !== null && (
        <Alert tono="error" titulo="No se pudo completar">
          {error}
        </Alert>
      )}

      {puedeGestionar && (
        <div className="fac-acciones">
          <Link href="/agenda/nuevo" className="boton boton--primario">
            Nuevo turno
          </Link>
        </div>
      )}

      <div className="dm-filtros">
        <Select
          id="agenda-recurso"
          etiqueta="Recurso"
          opciones={[
            { valor: "", etiqueta: "Todos los recursos" },
            ...recursos.map((uno) => ({ valor: uno.id, etiqueta: uno.nombre })),
          ]}
          value={filtros.recurso_id ?? ""}
          onChange={(evento) => void aplicar({ recurso_id: evento.target.value })}
        />
        <Campo
          id="agenda-desde"
          etiqueta="Desde"
          type="date"
          value={filtros.desde ?? ""}
          onChange={(evento) => void aplicar({ desde: evento.target.value })}
        />
        <Campo
          id="agenda-hasta"
          etiqueta="Hasta"
          type="date"
          value={filtros.hasta ?? ""}
          onChange={(evento) => void aplicar({ hasta: evento.target.value })}
        />
        <Select
          id="agenda-estado"
          etiqueta="Estado"
          opciones={ESTADOS}
          value={filtros.estado ?? ""}
          onChange={(evento) => void aplicar({ estado: evento.target.value })}
        />
      </div>

      <Tabla
        titulo="Turnos"
        columnas={columnas}
        filas={listado.turnos}
        claveDeFila={(fila) => fila.id}
        vacia={MENSAJE_SIN_TURNOS}
      />
    </>
  );
}
