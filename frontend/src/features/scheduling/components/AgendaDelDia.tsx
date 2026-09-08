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
 *
 * **El encabezado vive acá y no en `page.tsx`.** El CTA verde forma parte del encabezado —es lo
 * único que se hace desde esta pantalla— y quién puede verlo depende del rol, que es un dato
 * que este componente ya tiene. Partir el bloque en dos archivos para que el título esté en uno
 * y su botón en el otro deja dos lugares donde desalinear el mismo renglón.
 *
 * **Los nombres del cliente y del servicio son opcionales.** Un `Turno` viaja con ids; los
 * nombres los resuelve la página del servidor. Cuando no llegan —porque el cliente quedó fuera
 * de la página que el catálogo devolvió— se muestra el id, que es feo pero es cierto: una celda
 * vacía haría pensar que el turno está mal cargado.
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
  fechaLargaDe,
  horaDe,
  listarTurnos,
  tonoDeEstado,
} from "../api/turno";
import type { FiltrosDeAgenda, ListadoDeTurnos, Nombrado, Turno } from "../api/turno";
import type { Recurso } from "../api/recurso";
import { IconoDeMas } from "./iconos";

export interface PropsDeAgendaDelDia {
  readonly inicial: ListadoDeTurnos;
  readonly recursos: readonly Recurso[];
  /** Administrador y Operador reservan; Solo Lectura sólo mira (HU-E7-01 RN-03). */
  readonly puedeGestionar: boolean;
  /** Los clientes que el catálogo devolvió, para poner un nombre donde hay un id. */
  readonly clientes?: readonly Nombrado[];
  /** Ídem con los servicios agendables. */
  readonly servicios?: readonly Nombrado[];
  /**
   * El instante «ahora» del servidor, para el cintillo.
   *
   * Lo manda la página en vez de calcularlo acá para que el render del servidor y el del
   * navegador escriban el mismo día: dos `new Date()` a los lados de la medianoche no lo
   * hacen, y React descarta el HTML cuando el texto no coincide.
   */
  readonly hoy?: string;
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
  clientes = [],
  servicios = [],
  hoy,
}: PropsDeAgendaDelDia): JSX.Element {
  const [listado, setListado] = useState<ListadoDeTurnos>(inicial);
  const [filtros, setFiltros] = useState<FiltrosDeAgenda>({});
  const [error, setError] = useState<string | null>(null);

  const nombres = new Map(recursos.map((uno) => [uno.id, uno.nombre]));
  const nombresDeCliente = new Map(clientes.map((uno) => [uno.id, uno.nombre]));
  const nombresDeServicio = new Map(servicios.map((uno) => [uno.id, uno.nombre]));
  const cantidad = listado.turnos.length;

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
      // Monoespaciada y con cifras de ancho fijo: una agenda se lee bajando por la columna
      // de horas, y con tipografía proporcional los dos puntos de cada fila caen en un
      // lugar distinto.
      celda: (fila) => (
        <span className="age-hora">
          <b>{horaDe(fila.inicio)}</b>
          <span>hasta {horaDe(fila.fin)}</span>
        </span>
      ),
    },
    {
      clave: "fecha",
      titulo: "Fecha",
      celda: (fila) => <span className="age-fecha">{formatearFecha(fila.inicio)}</span>,
    },
    {
      clave: "cliente",
      titulo: "Cliente",
      // El nombre es también el enlace al turno: es lo que alguien busca en la fila cuando
      // atiende el teléfono, y por lo tanto lo que va a intentar apretar.
      celda: (fila) => (
        <Link className="age-quien" href={`/agenda/${fila.id}`}>
          {nombresDeCliente.get(fila.cliente_id) ?? fila.cliente_id}
        </Link>
      ),
    },
    {
      clave: "servicio",
      titulo: "Servicio",
      celda: (fila) => (
        <span className="age-dato">
          {nombresDeServicio.get(fila.servicio_id) ?? fila.servicio_id}
        </span>
      ),
    },
    {
      clave: "recurso",
      titulo: "Recurso",
      // El nombre y no el id: un id en una agenda no le dice nada a quien la mira. Si el
      // recurso no está en la lista —porque se desactivó y el filtro pide sólo activos—, el
      // id es mejor que una celda vacía.
      celda: (fila) => (
        <span className="age-dato age-dato--tenue">
          {nombres.get(fila.recurso_id) ?? fila.recurso_id}
        </span>
      ),
    },
    {
      clave: "estado",
      titulo: "Estado",
      celda: (fila) => (
        <Badge estado={tonoDeEstado(fila.estado)}>{ETIQUETAS_DE_ESTADO[fila.estado]}</Badge>
      ),
    },
    {
      clave: "ver",
      titulo: "",
      alDerecha: true,
      celda: (fila) => (
        // El chevron con nombre accesible: un enlace cuyo único contenido es «›» se anuncia
        // como «enlace, ›», que no dice a dónde va.
        <Link className="age-ver" href={`/agenda/${fila.id}`}>
          <span className="solo-lectores">Ver el turno de las {horaDe(fila.inicio)}</span>
          <span aria-hidden="true">›</span>
        </Link>
      ),
    },
  ];

  return (
    <div className="age-pantalla">
      <div className="age-encabezado">
        <div>
          <p className="age-encabezado__eyebrow">
            Operaciones · {fechaLargaDe(hoy ?? new Date().toISOString())}
          </p>
          <h1 className="age-encabezado__titulo">Agenda</h1>
          <p className="age-encabezado__intro">
            Los turnos del día en curso. Cambiá el rango o el recurso para ver otra cosa; un turno
            reprogramado aparece en su franja nueva conservando su estado.
          </p>
        </div>
        {puedeGestionar && (
          <div className="age-encabezado__acciones">
            <Link className="age-cta" href="/agenda/nuevo">
              <span aria-hidden="true" className="age-cta__icono">
                <IconoDeMas />
              </span>
              Nuevo turno
            </Link>
          </div>
        )}
      </div>

      {error !== null && (
        <Alert tono="error" titulo="No se pudo completar">
          {error}
        </Alert>
      )}

      <div className="age-filtros">
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

      <p className="age-cuenta">
        {cantidad} {cantidad === 1 ? "turno" : "turnos"}
      </p>

      {cantidad === 0 ? (
        // Corto y en una línea. La caja punteada de media pantalla que había antes decía lo
        // mismo y se leía como una carga que falló.
        <p className="age-vacio">{MENSAJE_SIN_TURNOS}</p>
      ) : (
        <div className="age-lista">
          <Tabla
            titulo="Turnos"
            columnas={columnas}
            filas={listado.turnos}
            claveDeFila={(fila) => fila.id}
            vacia={MENSAJE_SIN_TURNOS}
          />
        </div>
      )}
    </div>
  );
}
