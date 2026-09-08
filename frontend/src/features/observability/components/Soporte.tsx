/**
 * PAN-SOP-01 — Soporte · Nueva solicitud (HU-E9-03).
 *
 * El formulario de alta y el listado de lo abierto, que es lo que RN-04 deja consultar.
 *
 * **El mensaje de «el asunto y la descripción son obligatorios» lo escribe el backend.** Acá
 * el botón se deshabilita mientras falte alguno —que es cortesía— pero el texto que se muestra
 * cuando falla es el que vino, porque es la frase que el criterio pide palabra por palabra y
 * una copia local se desactualiza sin que nadie lo note.
 *
 * **No hay forma de cerrar un ticket desde el panel.** El estado lo mueve el equipo de
 * CheatSheet (RN-03): un botón de «resolver» del lado de la empresa convierte «resuelta» en
 * una opinión.
 *
 * **Formulario y listado conviven en dos columnas.** La tabla tiene cuatro columnas cortas; a
 * ancho completo del panel el asunto y su prioridad quedan a medio metro uno del otro y la
 * fecha se va contra el borde derecho de la pantalla. Con el formulario al lado, la fila
 * vuelve a un ancho que se lee de una pasada, y el asunto gana su descripción como segundo
 * renglón.
 */

"use client";

import { useState } from "react";

import { Alert, Badge, Button, Campo, Card, Select, Tabla, formatearFecha } from "@/shared";
import type { Columna } from "@/shared";

import {
  ETIQUETAS_DE_ESTADO,
  ErrorDeNotificacion,
  abrirSolicitud,
  listarSolicitudes,
} from "../api/notificaciones";
import type { PrioridadDeSoporte, Solicitud } from "../api/notificaciones";

export interface PropsDeSoporte {
  readonly inicial: readonly Solicitud[];
  /** HU-E9-03: el actor es el Administrador. El resto ve el estado de lo abierto. */
  readonly puedeAbrir: boolean;
}

const PRIORIDADES: readonly { valor: string; etiqueta: string }[] = [
  { valor: "BAJA", etiqueta: "Baja" },
  { valor: "MEDIA", etiqueta: "Media" },
  { valor: "ALTA", etiqueta: "Alta" },
];

/**
 * Las mismas etiquetas del selector, indexadas por el valor que viaja.
 *
 * Se derivan de `PRIORIDADES` en vez de repetirse: el listado tiene que mostrar exactamente lo
 * que el formulario ofrece, y dos listas paralelas se desincronizan en cuanto alguien agrega
 * una prioridad de un solo lado. Lo que la tabla no muestra nunca es el enum crudo: «MEDIA» en
 * mayúsculas es un valor de base de datos, no una palabra.
 */
const ETIQUETAS_DE_PRIORIDAD: Readonly<Record<string, string>> = Object.fromEntries(
  PRIORIDADES.map((una) => [una.valor, una.etiqueta]),
);

/** El punto de color de la prioridad. El texto la sigue diciendo: el color solo no informa. */
function claseDePunto(prioridad: PrioridadDeSoporte): string {
  if (prioridad === "ALTA") {
    return "log-prio__punto log-prio__punto--alta";
  }
  if (prioridad === "MEDIA") {
    return "log-prio__punto log-prio__punto--media";
  }
  return "log-prio__punto";
}

export function Soporte({ inicial, puedeAbrir }: PropsDeSoporte): JSX.Element {
  const [solicitudes, setSolicitudes] = useState<readonly Solicitud[]>(inicial);
  const [asunto, setAsunto] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const [prioridad, setPrioridad] = useState<PrioridadDeSoporte>("MEDIA");
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const completo = asunto.trim() !== "" && descripcion.trim() !== "";

  async function enviar(): Promise<void> {
    setEnviando(true);
    setError(null);
    setAviso(null);
    try {
      await abrirSolicitud({ asunto, descripcion, prioridad });
      setSolicitudes((await listarSolicitudes()).solicitudes);
      setAsunto("");
      setDescripcion("");
      setAviso("Tu solicitud quedó abierta. Te vamos a contestar por email.");
    } catch (fallo) {
      setError(
        fallo instanceof ErrorDeNotificacion ? fallo.message : "No se pudo abrir la solicitud.",
      );
    } finally {
      setEnviando(false);
    }
  }

  const columnas: readonly Columna<Solicitud>[] = [
    {
      clave: "asunto",
      titulo: "Asunto",
      // La descripción entra como segundo renglón: es lo que distingue dos solicitudes que se
      // llamaron parecido, y la columna tenía ancho de sobra para cargarla.
      celda: (fila) => (
        <span className="log-sol">
          <b>{fila.asunto}</b>
          <span>{fila.descripcion}</span>
        </span>
      ),
    },
    {
      clave: "prioridad",
      titulo: "Prioridad",
      celda: (fila) => (
        <span className="log-prio">
          <span className={claseDePunto(fila.prioridad)} aria-hidden="true" />
          {ETIQUETAS_DE_PRIORIDAD[fila.prioridad] ?? fila.prioridad}
        </span>
      ),
    },
    {
      clave: "estado",
      titulo: "Estado",
      celda: (fila) => (
        <Badge estado={fila.esta_abierta ? "pendiente" : "ok"}>
          {ETIQUETAS_DE_ESTADO[fila.estado] ?? fila.estado}
        </Badge>
      ),
    },
    {
      clave: "creada",
      titulo: "Abierta el",
      // Sin alinear a la derecha: es la última de cuatro columnas cortas, y empujarla contra
      // el borde es justamente lo que dejaba la fecha lejos de la fila que fecha.
      celda: (fila) => (
        <span className="log-fecha">
          {fila.created_at !== null ? formatearFecha(fila.created_at) : "—"}
        </span>
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
      {aviso !== null && <Alert tono="exito">{aviso}</Alert>}

      <div className={`log-soporte${puedeAbrir ? "" : " log-soporte--sola"}`}>
        {puedeAbrir && (
          <Card titulo="Nueva solicitud">
            <Campo
              id="sop-asunto"
              etiqueta="Asunto"
              value={asunto}
              onChange={(evento) => setAsunto(evento.target.value)}
            />
            {/*
             * El catálogo compartido no tiene área de texto y ésta es la única pantalla del
             * panel que necesita una, así que se arma con la envoltura del catálogo —`.campo`
             * y su etiqueta— y un control propio, `.log-area`, que hereda el mismo borde,
             * radio y foco de acento que cualquier otro campo.
             */}
            <div className="campo">
              <label className="campo__etiqueta" htmlFor="sop-descripcion">
                Descripción
              </label>
              <textarea
                id="sop-descripcion"
                className="log-area"
                rows={4}
                placeholder="Qué pasó, en qué pantalla y desde cuándo."
                value={descripcion}
                onChange={(evento) => setDescripcion(evento.target.value)}
              />
            </div>
            <Select
              id="sop-prioridad"
              etiqueta="Prioridad"
              opciones={PRIORIDADES}
              value={prioridad}
              onChange={(evento) => setPrioridad(evento.target.value as PrioridadDeSoporte)}
            />
            {/* La acción de cierre va a la derecha, donde termina de leerse el formulario. */}
            <div className="log-soporte__pie">
              <Button onClick={() => void enviar()} cargando={enviando} disabled={!completo}>
                Enviar
              </Button>
            </div>
          </Card>
        )}

        <Card titulo="Mis solicitudes">
          <Tabla
            titulo="Solicitudes de soporte"
            columnas={columnas}
            filas={solicitudes}
            claveDeFila={(fila) => fila.id}
            vacia="Todavía no abriste ninguna solicitud."
          />
        </Card>
      </div>
    </>
  );
}
