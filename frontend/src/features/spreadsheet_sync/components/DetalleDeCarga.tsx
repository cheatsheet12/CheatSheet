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
 * **Los tres números van juntos y del mismo tamaño**, como en el prototipo. Totales,
 * procesadas y con error sólo significan algo comparados entre sí: 4 con error es una
 * anécdota sobre 142 filas y un desastre sobre 6.
 *
 * `puede_reprocesar` viene del backend y ya contempla las dos razones por las que no se
 * puede: el rol es Solo Lectura (RN-04) o no hay filas que corregir.
 */

"use client";

import { useState } from "react";

import { Alert, Badge, Button, Card, Desplegable, Tabla, formatearFechaHora } from "@/shared";
import type { Columna, EstadoDeBadge } from "@/shared";

import {
  ETIQUETAS_DE_ESTADO,
  ErrorDePlanilla,
  csvDeErrores,
  reprocesarCarga,
  verCarga,
} from "../api/planilla";
import { CorreccionDeFila } from "./CorreccionDeFila";
import { Icono } from "./iconos";
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

/**
 * Las columnas de «Filas con error». Una fila **corregida** no desaparece: queda como historia,
 * con su marca, porque el detalle de una carga es el registro de lo que pasó con ella.
 */
function columnasDeErrores(
  puedeCorregir: boolean,
  alCorregir: (numeroFila: number) => void,
): readonly Columna<ErrorDeFila>[] {
  return [
    {
      clave: "fila",
      titulo: "Fila",
      celda: (e) => (
        <span className={e.corregida ? "ing-proc-fila ing-proc-fila--corregida" : "ing-proc-fila"}>
          {e.numero_fila}
        </span>
      ),
    },
    {
      clave: "motivo",
      titulo: "Motivo",
      celda: (e) => (
        <span
          className={e.corregida ? "ing-proc-motivo ing-proc-motivo--corregida" : "ing-proc-motivo"}
        >
          {e.motivo}
        </span>
      ),
    },
    {
      clave: "accion",
      titulo: "",
      alDerecha: true,
      celda: (e) =>
        e.corregida ? (
          <Badge estado="ok">Corregida</Badge>
        ) : puedeCorregir ? (
          <Button
            variante="secundario"
            onClick={() => {
              alCorregir(e.numero_fila);
            }}
          >
            <Icono nombre="editar" />
            Corregir
          </Button>
        ) : null,
    },
  ];
}

export function DetalleDeCarga({ inicial }: PropsDeDetalle): JSX.Element {
  const [detalle, setDetalle] = useState<Detalle>(inicial);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [trabajando, setTrabajando] = useState(false);
  const [editando, setEditando] = useState<number | null>(null);

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
          : "No se pudo completar la operación",
      );
    } finally {
      setTrabajando(false);
    }
  }

  function descargar(): void {
    const blob = new Blob([csvDeErrores(detalle.errores.filter((e) => !e.corregida))], {
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
  const hayPendientes = detalle.errores.some((e) => !e.corregida);

  function alCorregir(nuevo: Detalle, numeroFila: number): void {
    setDetalle(nuevo);
    setEditando(null);
    setError(null);
    setAviso(`Se corrigió la fila ${numeroFila} y se importó.`);
  }

  return (
    <>
      {error !== null && <Alert tono="error">{error}</Alert>}
      {aviso !== null && <Alert tono="exito">{aviso}</Alert>}
      {carga.estado === "FALLIDO" && (
        <Alert tono="error">
          No se pudo leer la planilla: {detalle.errores[0]?.motivo ?? "intentá procesarla de nuevo"}
          . Revisá la conexión o la hoja de origen y volvé a procesar desde Planillas.
        </Alert>
      )}

      <div className="ing-tarjetas">
        <Card>
          <p className="ing-estado-carga">
            <Badge estado={TONO[carga.estado]}>{ETIQUETAS_DE_ESTADO[carga.estado]}</Badge>
            <span className="ing-carga__ref">{formatearFechaHora(carga.created_at)}</span>
            {carga.es_reproceso && (
              <span className="ing-carga__ref">reproceso de una carga anterior</span>
            )}
          </p>

          {/* Los tres números de RN-01. Una lista de definiciones y no una tabla: son tres pares
            etiqueta/valor, y una tabla de una fila le miente al lector de pantalla sobre lo que
            está mirando. */}
          <dl className="ing-proc-stats">
            <div className="ing-proc-stat">
              <dd className="ing-proc-stat__n">{carga.filas_totales}</dd>
              <dt className="ing-proc-stat__l">
                <span className="ing-proc-stat__ico">
                  <Icono nombre="lista" />
                </span>
                Filas totales
              </dt>
            </div>
            <div className="ing-proc-stat ing-proc-stat--ok">
              <dd className="ing-proc-stat__n">{carga.filas_ok}</dd>
              <dt className="ing-proc-stat__l">
                <span className="ing-proc-stat__ico">
                  <Icono nombre="tilde" />
                </span>
                Procesadas
              </dt>
            </div>
            <div className="ing-proc-stat ing-proc-stat--error">
              <dd className="ing-proc-stat__n">{carga.filas_error}</dd>
              <dt className="ing-proc-stat__l">
                <span className="ing-proc-stat__ico">
                  <Icono nombre="alerta" />
                </span>
                Con error
              </dt>
            </div>
          </dl>
        </Card>

        {carga.estado !== "FALLIDO" && (
          <Card>
            <div className="ing-seccion">
              <div>
                <h2 className="ing-seccion__titulo">Filas con error</h2>
                <p className="ing-seccion__sub">
                  El número de fila es el de tu planilla original, para que lo busques en el margen
                </p>
              </div>
            </div>
            <div className="ing-proc-errores">
              <Tabla
                titulo="Filas con error"
                columnas={columnasDeErrores(
                  detalle.puede_reprocesar && detalle.puede_corregir_filas !== false,
                  setEditando,
                )}
                filas={detalle.errores}
                claveDeFila={(e) => String(e.numero_fila)}
                vacia="Esta carga no dejó ninguna fila con error."
              />
            </div>

            {detalle.puede_reprocesar && (
              // Lo que el reproceso hace y lo que no, dicho antes de apretar el botón: sin esto,
              // «reprocesar» se lee como «volver a subir todo» y nadie lo toca por miedo a duplicar
              // (HU-E3-06 RN-01 y RN-02).
              <Desplegable titulo="Qué hace reprocesar" variante="simple">
                {detalle.puede_corregir_filas === false
                  ? "Arreglá los datos en tu planilla de Google y reprocesá: el sistema reutiliza el mapeo confirmado e incorpora sólo las filas pendientes."
                  : "Podés corregir cada fila desde acá, o arreglar los datos en tu planilla y reprocesar: el sistema reutiliza el mapeo confirmado e incorpora sólo las filas pendientes, sin duplicar las ya procesadas ni las que corregiste."}
              </Desplegable>
            )}

            <div className="ing-acciones">
              {detalle.puede_reprocesar && (
                <Button
                  disabled={trabajando}
                  cargando={trabajando}
                  onClick={() => {
                    void reprocesar();
                  }}
                >
                  <Icono nombre="refrescar" />
                  Reprocesar las filas con error
                </Button>
              )}
              {hayPendientes && (
                <Button variante="secundario" onClick={descargar}>
                  <Icono nombre="descargar" />
                  Descargar el listado de errores
                </Button>
              )}
            </div>
          </Card>
        )}
      </div>

      <CorreccionDeFila
        cargaId={detalle.carga.id}
        numeroFila={editando}
        alCerrar={() => {
          setEditando(null);
        }}
        alCorregir={alCorregir}
      />
    </>
  );
}
