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
 *
 * **Hay un solo estado vacío.** Antes había dos, uno debajo del otro: «No tenés notificaciones
 * sin leer» y, en la caja punteada de ancho completo, «No tenés notificaciones». La segunda
 * frase implica la primera, y esa caja ocupaba casi toda la pantalla para decir que no pasó
 * nada. El resumen de no leídas sólo tiene sentido cuando hay algo que contar.
 */

"use client";

import { useState } from "react";

import { Alert, Badge, Card, formatearFechaHora } from "@/shared";

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

/**
 * RN-01 pide que la severidad se vea. El enum no se muestra crudo: «ALTA» es el valor que
 * viaja, no una palabra que alguien escriba en una pantalla.
 */
const ETIQUETAS_DE_SEVERIDAD: Readonly<Record<string, string>> = {
  ALTA: "Severidad alta",
  MEDIA: "Severidad media",
  BAJA: "Severidad baja",
};

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

  if (listado.notificaciones.length === 0) {
    return (
      <>
        {error !== null && (
          <Alert tono="error" titulo="No se pudo completar">
            {error}
          </Alert>
        )}
        {/* Una raya corta y un renglón, dentro de la tarjeta: el mismo tratamiento que la
            operación sin datos registrados en PAN-LOG-02. La envoltura la acota para que la
            tarjeta no vuelva a ser la caja gigante que se acaba de sacar de la pantalla. */}
        <div className="log-bandeja__vacia">
          <Card>
            <p className="log-nada">{MENSAJE_SIN_NOTIFICACIONES}</p>
          </Card>
        </div>
      </>
    );
  }

  return (
    <>
      {error !== null && (
        <Alert tono="error" titulo="No se pudo completar">
          {error}
        </Alert>
      )}

      <p className="log-bandeja__resumen">
        {listado.no_leidas === 0
          ? "No tenés notificaciones sin leer."
          : `Tenés ${listado.no_leidas} notificación${listado.no_leidas === 1 ? "" : "es"} sin leer.`}
      </p>

      <ul className="log-bandeja">
        {listado.notificaciones.map((una) => (
          <li key={una.id}>
            {/*
             * La tarjeta es propia y no el `Card` compartido porque su fondo y su borde
             * cambian al marcarla leída, y una transición sólo existe si el elemento que la
             * sufre es el mismo antes y después.
             */}
            <article
              className={`log-aviso${una.se_destaca ? " log-aviso--destacado" : ""}${
                una.leida ? " log-aviso--leida" : ""
              }`}
            >
              <p className="log-aviso__cab">
                <Badge estado={una.se_destaca ? "error" : "pendiente"}>
                  {ETIQUETAS_DE_CATEGORIA[una.categoria] ?? una.categoria}
                </Badge>
                <span className="log-aviso__sev">
                  {ETIQUETAS_DE_SEVERIDAD[una.severidad] ?? una.severidad}
                </span>
                {una.se_destaca && <span className="log-aviso__urgente">Requiere atención</span>}
                {una.created_at !== null && (
                  <span className="log-aviso__fecha">{formatearFechaHora(una.created_at)}</span>
                )}
              </p>
              <p className="log-aviso__cuerpo">{una.cuerpo}</p>
              <div className="log-aviso__pie">
                {una.leida ? (
                  <p className="log-aviso__leida">Leída</p>
                ) : (
                  // Acción de fila: texto, como el resto del panel. Un botón con caja por
                  // tarjeta arma una columna de botones que pesa más que los avisos mismos.
                  <button
                    type="button"
                    className="log-aviso__accion"
                    onClick={() => void leer(una)}
                  >
                    Marcar como leída
                  </button>
                )}
              </div>
            </article>
          </li>
        ))}
      </ul>
    </>
  );
}
