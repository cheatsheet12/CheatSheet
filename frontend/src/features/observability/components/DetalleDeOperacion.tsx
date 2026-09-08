/**
 * PAN-LOG-02 — Log de Operaciones · Detalle (HU-E12-02).
 *
 * El resumen, lo que la operación registró de sí misma, y el **timeline**: los pasos que le
 * pasaron a la misma entidad, en orden, con el que falló señalado.
 *
 * **Cuando no hay detalle, se dice.** Casi ninguna operación registra datos de entrada o la
 * respuesta de un servicio externo, y la pantalla lo declara en vez de dibujar una sección
 * vacía que parece un error de carga. La que sí lo registra es la autorización de un
 * comprobante, que es la que RN-02 nombra: CAE, número y estado.
 *
 * **Sin duración cuando la operación dejó una sola fila.** Mostrar «0 ms» sería afirmar algo
 * que nadie midió.
 */

"use client";

import { Alert, Badge, Card, Tabla, formatearFechaHora } from "@/shared";
import type { Columna, EstadoDeBadge } from "@/shared";

import {
  ETIQUETAS_DE_INICIADOR,
  ETIQUETAS_DE_MODULO,
  ETIQUETAS_DE_RESULTADO,
} from "../api/bitacora";
import type { DetalleDeOperacion as Detalle, Operacion } from "../api/bitacora";

export interface PropsDeDetalleDeOperacion {
  readonly detalle: Detalle;
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

export function DetalleDeOperacion({ detalle }: PropsDeDetalleDeOperacion): JSX.Element {
  const { operacion } = detalle;
  const entradas = Object.entries(detalle.detalle);

  const columnas: readonly Columna<Operacion>[] = [
    { clave: "momento", titulo: "Momento", celda: (fila) => formatearFechaHora(fila.timestamp) },
    { clave: "paso", titulo: "Paso", celda: (fila) => fila.accion },
    {
      clave: "resultado",
      titulo: "Resultado",
      celda: (fila) => (
        <Badge estado={tonoDe(fila.resultado)}>{ETIQUETAS_DE_RESULTADO[fila.resultado]}</Badge>
      ),
    },
  ];

  return (
    <>
      {detalle.paso_con_error !== null && (
        <Alert tono="error" titulo="La operación falló">
          El timeline marca en qué paso ocurrió.
        </Alert>
      )}

      <Card titulo="Resumen">
        <dl className="log-resumen">
          <dt>Operación</dt>
          <dd>{operacion.accion}</dd>
          <dt>Módulo</dt>
          <dd>{ETIQUETAS_DE_MODULO[operacion.modulo] ?? operacion.modulo}</dd>
          <dt>Entidad afectada</dt>
          <dd>{operacion.entidad_afectada}</dd>
          <dt>Iniciador</dt>
          <dd>{ETIQUETAS_DE_INICIADOR[operacion.iniciador]}</dd>
          <dt>Momento</dt>
          <dd>{formatearFechaHora(operacion.timestamp)}</dd>
          <dt>Duración</dt>
          <dd>{duracion(detalle.duracion_ms)}</dd>
          <dt>Estado final</dt>
          <dd>
            <Badge estado={tonoDe(operacion.resultado)}>
              {ETIQUETAS_DE_RESULTADO[operacion.resultado]}
            </Badge>
          </dd>
        </dl>
      </Card>

      <Card titulo="Datos registrados">
        {entradas.length === 0 ? (
          <p className="tabla__vacia">Esta operación no registró datos adicionales.</p>
        ) : (
          <dl className="log-resumen">
            {entradas.map(([clave, valor]) => (
              <div key={clave} className="log-resumen__par">
                <dt>{clave}</dt>
                <dd>{valor}</dd>
              </div>
            ))}
          </dl>
        )}
      </Card>

      <Card titulo="Timeline de ejecución">
        <Tabla
          titulo="Pasos de la operación"
          columnas={columnas}
          filas={detalle.timeline}
          claveDeFila={(fila) => fila.id}
          vacia="Esta operación no dejó pasos registrados."
        />
      </Card>
    </>
  );
}
