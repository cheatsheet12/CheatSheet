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
    { clave: "asunto", titulo: "Asunto", celda: (fila) => fila.asunto },
    { clave: "prioridad", titulo: "Prioridad", celda: (fila) => fila.prioridad },
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
      celda: (fila) => (fila.created_at !== null ? formatearFecha(fila.created_at) : "—"),
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

      {puedeAbrir && (
        <Card titulo="Nueva solicitud">
          <Campo
            id="sop-asunto"
            etiqueta="Asunto"
            value={asunto}
            onChange={(evento) => setAsunto(evento.target.value)}
          />
          <label className="campo" htmlFor="sop-descripcion">
            <span className="campo__etiqueta">Descripción</span>
            <textarea
              id="sop-descripcion"
              className="campo__control"
              rows={5}
              value={descripcion}
              onChange={(evento) => setDescripcion(evento.target.value)}
            />
          </label>
          <Select
            id="sop-prioridad"
            etiqueta="Prioridad"
            opciones={PRIORIDADES}
            value={prioridad}
            onChange={(evento) => setPrioridad(evento.target.value as PrioridadDeSoporte)}
          />
          <Button onClick={() => void enviar()} cargando={enviando} disabled={!completo}>
            Enviar
          </Button>
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
    </>
  );
}
