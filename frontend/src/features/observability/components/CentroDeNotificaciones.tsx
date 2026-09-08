/**
 * PAN-CFG-NOT — Configuración · Notificaciones (HU-E11-03).
 *
 * La bandeja de quien está mirando, y sólo la suya. Con su categoría, su severidad y su estado
 * de lectura (RN-01), y lo de severidad alta **destacado** (RN-04).
 *
 * **Solo Lectura entra acá.** RN-05 le niega las acciones de gestión, y marcar como leída una
 * notificación propia no es gestión: es acuse de recibo. Lo que ese rol no ve es la bitácora,
 * que es otra pantalla y otra decisión.
 *
 * **Lo destacado deja de destacarse al leerlo.** Una alta ya leída que sigue en rojo enseña a
 * ignorar el rojo, que es exactamente lo contrario de lo que RN-04 quiere.
 */

"use client";

import { useState } from "react";

import { Alert, Badge, Button, Card, formatearFechaHora } from "@/shared";

import {
  ETIQUETAS_DE_CATEGORIA,
  ErrorDeNotificacion,
  MENSAJE_SIN_NOTIFICACIONES,
  marcarComoLeida,
} from "../api/notificaciones";
import type { ListadoDeNotificaciones, Notificacion } from "../api/notificaciones";

export interface PropsDeCentroDeNotificaciones {
  readonly inicial: ListadoDeNotificaciones;
}

export function CentroDeNotificaciones({ inicial }: PropsDeCentroDeNotificaciones): JSX.Element {
  const [listado, setListado] = useState<ListadoDeNotificaciones>(inicial);
  const [error, setError] = useState<string | null>(null);

  async function leer(notificacion: Notificacion): Promise<void> {
    setError(null);
    try {
      const marcada = await marcarComoLeida(notificacion.id);
      setListado({
        notificaciones: listado.notificaciones.map((una) =>
          una.id === marcada.id ? marcada : una,
        ),
        no_leidas: Math.max(0, listado.no_leidas - 1),
      });
    } catch (fallo) {
      setError(
        fallo instanceof ErrorDeNotificacion
          ? fallo.message
          : "No se pudo marcar la notificación como leída.",
      );
    }
  }

  return (
    <>
      {error !== null && (
        <Alert tono="error" titulo="No se pudo completar">
          {error}
        </Alert>
      )}

      <p className="dm-intro">
        {listado.no_leidas === 0
          ? "No tenés notificaciones sin leer."
          : `Tenés ${listado.no_leidas} notificación${listado.no_leidas === 1 ? "" : "es"} sin leer.`}
      </p>

      {listado.notificaciones.length === 0 ? (
        <p className="tabla__vacia">{MENSAJE_SIN_NOTIFICACIONES}</p>
      ) : (
        <ul className="log-avisos">
          {listado.notificaciones.map((una) => (
            <li key={una.id}>
              <Card>
                <p className="log-avisos__encabezado">
                  <Badge estado={una.se_destaca ? "error" : "pendiente"}>
                    {ETIQUETAS_DE_CATEGORIA[una.categoria] ?? una.categoria}
                  </Badge>
                  {una.se_destaca && <span className="log-avisos__urgente">Requiere atención</span>}
                  {una.created_at !== null && (
                    <span className="rep-comparacion">{formatearFechaHora(una.created_at)}</span>
                  )}
                </p>
                <p>{una.cuerpo}</p>
                {una.leida ? (
                  <p className="rep-comparacion">Leída</p>
                ) : (
                  <Button variante="secundario" onClick={() => void leer(una)}>
                    Marcar como leída
                  </Button>
                )}
              </Card>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
