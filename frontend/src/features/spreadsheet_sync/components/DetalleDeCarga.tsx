/**
 * PAN-ING-03 — Ingesta de Datos · Detalle de procesamiento (HU-E3-05, HU-E3-06).
 *
 * Tres cosas que la historia pide y que están acá:
 *
 * - **el resumen de filas totales, procesadas y con error** (RN-01);
 * - **cada fila fallida con su número original y su motivo** (RN-02) — el número que el
 *   usuario va a buscar en el margen de su propia planilla;
 * - **la descarga del listado de errores** (RN-03), armada en el navegador: los datos ya
 *   están en pantalla, y pedirlos otra vez al backend sería la misma tabla viajando dos
 *   veces para producir un archivo que el navegador escribe solo.
 *
 * `puede_reprocesar` viene del backend y ya contempla las dos razones por las que no se
 * puede: el rol es Solo Lectura (RN-04) o no hay filas que corregir.
 */

"use client";

import { useState } from "react";

import { Alert, Badge, Button, Tabla } from "@/shared";
import type { Columna, EstadoDeBadge } from "@/shared";

import {
  ETIQUETAS_DE_ESTADO,
  ErrorDePlanilla,
  csvDeErrores,
  reprocesarCarga,
  verCarga,
} from "../api/planilla";
import type { DetalleDeCarga as Detalle, ErrorDeFila, EstadoProcesamiento } from "../api/planilla";

export interface PropsDeDetalle {
  readonly inicial: Detalle;
}

const TONO: Readonly<Record<EstadoProcesamiento, EstadoDeBadge>> = {
  EN_CURSO: "pendiente",
  COMPLETADO: "ok",
  CON_ERRORES: "atencion",
  FALLIDO: "error",
};

const COLUMNAS: readonly Columna<ErrorDeFila>[] = [
  { clave: "fila", titulo: "Fila", celda: (e) => e.numero_fila },
  { clave: "motivo", titulo: "Motivo", celda: (e) => e.motivo },
];

export function DetalleDeCarga({ inicial }: PropsDeDetalle): JSX.Element {
  const [detalle, setDetalle] = useState<Detalle>(inicial);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [trabajando, setTrabajando] = useState(false);

  async function reprocesar(): Promise<void> {
    setError(null);
    setAviso(null);
    setTrabajando(true);
    try {
      await reprocesarCarga(detalle.carga.id);
      setAviso(
        "Encolamos el reproceso de las filas con error. En unos minutos vas a ver una carga nueva.",
      );
      setDetalle(await verCarga(detalle.carga.id));
    } catch (problema) {
      setError(
        problema instanceof ErrorDePlanilla
          ? problema.message
          : "No se pudo completar la operacion",
      );
    } finally {
      setTrabajando(false);
    }
  }

  function descargar(): void {
    const blob = new Blob([csvDeErrores(detalle.errores)], {
      type: "text/csv;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const enlace = document.createElement("a");
    enlace.href = url;
    enlace.download = `errores-${detalle.carga.id}.csv`;
    enlace.click();
    // Sin esto el blob queda vivo hasta que se cierra la pestaña, y en una pantalla que
    // se usa varias veces seguidas eso es memoria que nadie recupera.
    URL.revokeObjectURL(url);
  }

  const { carga } = detalle;

  return (
    <>
      {error !== null && <Alert tono="error">{error}</Alert>}
      {aviso !== null && <Alert tono="exito">{aviso}</Alert>}

      <p>
        <Badge estado={TONO[carga.estado]}>{ETIQUETAS_DE_ESTADO[carga.estado]}</Badge>
        {carga.es_reproceso && " · reproceso de una carga anterior"}
      </p>

      <dl className="resumen-de-carga">
        <dt>Filas totales</dt>
        <dd>{carga.filas_totales}</dd>
        <dt>Procesadas</dt>
        <dd>{carga.filas_ok}</dd>
        <dt>Con error</dt>
        <dd>{carga.filas_error}</dd>
      </dl>

      <Tabla
        titulo="Filas con error"
        columnas={COLUMNAS}
        filas={detalle.errores}
        claveDeFila={(e) => String(e.numero_fila)}
        vacia="Esta carga no dejo ninguna fila con error."
      />

      {detalle.errores.length > 0 && (
        <Button variante="secundario" onClick={descargar}>
          Descargar el listado de errores
        </Button>
      )}

      {detalle.puede_reprocesar && (
        <Button
          disabled={trabajando}
          cargando={trabajando}
          onClick={() => {
            void reprocesar();
          }}
        >
          Reprocesar las filas con error
        </Button>
      )}
    </>
  );
}
