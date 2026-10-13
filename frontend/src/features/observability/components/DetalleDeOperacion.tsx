/**
 * PAN-LOG-02 — Log de Operaciones · Detalle (HU-E12-02).
 *
 * El resumen, lo que la operación registró de sí misma, y el **timeline**: los pasos que le
 * pasaron a la misma entidad, en orden, con el que falló señalado.
 *
 * **Nada se dice dos veces.** La tira de arriba —momento, estado, iniciador, duración— es lo
 * que se lee de un vistazo; el resumen de abajo es lo que hay que ir a buscar. Repetir la
 * duración en las dos obliga a comprobar que digan lo mismo, que es trabajo que la pantalla
 * le está pasando al lector.
 *
 * **Cuando no hay detalle, se dice en una línea.** Casi ninguna operación registra datos de
 * entrada o la respuesta de un servicio externo, y una tarjeta vacía de media pantalla se lee
 * como una carga que falló. La que sí lo registra es la autorización de un comprobante, que
 * es la que RN-02 nombra: CAE, número y estado.
 *
 * **Sin duración cuando la operación dejó una sola fila.** Mostrar «0 ms» sería afirmar algo
 * que nadie midió.
 */

"use client";

import { CircleAlert, ScrollText } from "lucide-react";

import { Alert, Badge, formatearFechaHora } from "@/shared";
import type { EstadoDeBadge } from "@/shared";

import { ETIQUETAS_DE_MODULO, ETIQUETAS_DE_RESULTADO } from "../api/bitacora";
import type { DetalleDeOperacion as Detalle, Operacion } from "../api/bitacora";
import { nombreDeAccion } from "./formato";
import { MarcaDeIniciador } from "./MarcasDeOperacion";
import { TimelineDeEjecucion } from "./TimelineDeEjecucion";

/** Quién hizo la operación, resuelto del lado del servidor desde los usuarios de la empresa (#169). */
export interface ResponsableDeOperacion {
  readonly nombre: string;
  readonly email: string;
}

export interface PropsDeDetalleDeOperacion {
  readonly detalle: Detalle;
  /**
   * El usuario que la ejecutó. `null` o ausente cuando no se pudo resolver: entonces se muestra
   * el id, que es feo pero es cierto — una celda vacía haría pensar que no hubo responsable.
   */
  readonly responsable?: ResponsableDeOperacion | null;
}

function textoDelResponsable(
  usuarioId: string | null,
  responsable: ResponsableDeOperacion | null,
): string {
  if (usuarioId === null) {
    return "Sin usuario: la ejecutó la plataforma";
  }
  return responsable === null ? usuarioId : `${responsable.nombre} · ${responsable.email}`;
}

function tonoDe(resultado: Operacion["resultado"]): EstadoDeBadge {
  return resultado === "error" ? "error" : "ok";
}

function duracion(ms: number | null): string {
  if (ms === null) {
    return "No registrada";
  }
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

interface PropsDePar {
  readonly clave: string;
  readonly mono?: boolean;
  readonly children: React.ReactNode;
}

function Par({ clave, mono = false, children }: PropsDePar): JSX.Element {
  return (
    <div className="log-kv__par">
      <dt className="log-kv__k">{clave}</dt>
      <dd className={`log-kv__v${mono ? " log-kv__v--mono" : ""}`}>{children}</dd>
    </div>
  );
}

export function DetalleDeOperacion({
  detalle,
  responsable = null,
}: PropsDeDetalleDeOperacion): JSX.Element {
  const { operacion } = detalle;
  const entradas = Object.entries(detalle.detalle);

  return (
    <div className="log-detalle">
      {detalle.paso_con_error !== null && (
        <Alert tono="error" titulo="La operación falló">
          El timeline marca en qué paso ocurrió.
        </Alert>
      )}

      <section className="log-tarjeta">
        <div className="log-cabecera">
          <span
            className={`log-cabecera__icono${operacion.resultado === "error" ? " log-cabecera__icono--error" : ""}`}
            aria-hidden="true"
          >
            {operacion.resultado === "error" ? (
              <CircleAlert size={26} strokeWidth={1.8} />
            ) : (
              <ScrollText size={26} strokeWidth={1.8} />
            )}
          </span>
          <div className="log-cabecera__texto">
            <p className="log-cabecera__linea">
              <Badge estado="pendiente">
                {ETIQUETAS_DE_MODULO[operacion.modulo] ?? operacion.modulo}
              </Badge>
            </p>
            <h2 className="log-cabecera__titulo">{nombreDeAccion(operacion.accion)}</h2>
            <code className="log-cabecera__codigo">{operacion.accion}</code>
            <p className="log-cabecera__sub">{operacion.entidad_afectada}</p>
          </div>
        </div>

        <div className="log-meta">
          <div>
            <p className="log-meta__l">Momento</p>
            <p className="log-meta__v log-meta__v--mono">
              {formatearFechaHora(operacion.timestamp)}
            </p>
          </div>
          <div>
            <p className="log-meta__l">Estado</p>
            <p className="log-meta__v">
              <Badge estado={tonoDe(operacion.resultado)}>
                {ETIQUETAS_DE_RESULTADO[operacion.resultado]}
              </Badge>
            </p>
          </div>
          <div>
            <p className="log-meta__l">Iniciado por</p>
            <p className="log-meta__v">
              <MarcaDeIniciador iniciador={operacion.iniciador} />
            </p>
          </div>
          <div>
            <p className="log-meta__l">Duración</p>
            <p className="log-meta__v log-meta__v--mono">{duracion(detalle.duracion_ms)}</p>
          </div>
        </div>
      </section>

      <section className="log-tarjeta log-seccion">
        <h2 className="log-seccion__titulo">Resumen de la operación</h2>
        <dl className="log-kv">
          <Par clave="Identificador" mono>
            {operacion.id}
          </Par>
          <Par clave="Entidad afectada" mono>
            {operacion.entidad_afectada}
          </Par>
          <Par clave="Responsable">{textoDelResponsable(operacion.usuario_id, responsable)}</Par>
        </dl>
      </section>

      <section className="log-tarjeta log-seccion">
        <h2 className="log-seccion__titulo">
          Datos registrados
          <span className="log-seccion__nota">Lo que la operación guardó de sí misma</span>
        </h2>
        {entradas.length === 0 ? (
          <p className="log-nada">Esta operación no registró datos adicionales.</p>
        ) : (
          <dl className="log-kv">
            {entradas.map(([clave, valor]) => (
              <Par key={clave} clave={clave} mono>
                {valor}
              </Par>
            ))}
          </dl>
        )}
      </section>

      <section className="log-tarjeta log-seccion">
        <h2 className="log-seccion__titulo">
          Timeline de ejecución
          <span className="log-seccion__nota">Los pasos internos, en orden</span>
        </h2>
        {detalle.timeline.length === 0 ? (
          <p className="log-nada">Esta operación no dejó pasos registrados.</p>
        ) : (
          <TimelineDeEjecucion pasos={detalle.timeline} pasoConError={detalle.paso_con_error} />
        )}
      </section>
    </div>
  );
}
