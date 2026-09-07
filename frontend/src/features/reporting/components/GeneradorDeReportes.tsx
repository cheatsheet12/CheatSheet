/**
 * PAN-REP-01 — previsualizar, generar y descargar (HU-E10-02 y HU-E10-03).
 *
 * **La previsualización se pide al cambiar cualquier filtro, y no genera nada** (HU-E10-02
 * RN-03). Es la misma consulta que el tablero con otro nombre: cuántos y por cuánto. Ajustar
 * un filtro cinco veces cuesta cinco consultas y cero reportes en el historial.
 *
 * **Los formatos que se ofrecen dependen del tipo.** Un resumen ejecutivo en CSV son cuatro
 * números sin gráfico y un listado de facturación en PDF de un mes ocupado son ochenta páginas
 * que nadie lee: el backend los rechaza, y ofrecerlos acá sería hacer que alguien lo descubra
 * apretando el botón.
 *
 * **El historial no se borra.** Es lo que contesta «qué le mandé a mi contador y cuándo».
 */

"use client";

import { useState } from "react";

import { Alert, Badge, Button, Campo, Card, Select, Tabla } from "@/shared";
import type { Columna, EstadoDeBadge } from "@/shared";

import {
  ETIQUETAS_DE_TIPO,
  ErrorDeReporte,
  FORMATOS_POR_TIPO,
  generarReporte,
  listarReportes,
  previsualizar,
  urlDeReporte,
} from "../api/reporte";
import type {
  FormatoReporte,
  Previsualizacion,
  RangoDePeriodo,
  Reporte,
  TipoReporte,
} from "../api/reporte";

export interface PropsDeGeneradorDeReportes {
  readonly inicial: readonly Reporte[];
  readonly periodo: RangoDePeriodo;
  /** Administrador y Operador generan; Solo Lectura y el contador sólo miran el tablero. */
  readonly puedeGenerar: boolean;
}

const TIPOS: readonly { valor: TipoReporte; etiqueta: string }[] = [
  { valor: "FACTURACION", etiqueta: ETIQUETAS_DE_TIPO.FACTURACION },
  { valor: "COBROS", etiqueta: ETIQUETAS_DE_TIPO.COBROS },
  { valor: "OPERACIONES", etiqueta: ETIQUETAS_DE_TIPO.OPERACIONES },
  { valor: "RESUMEN_EJECUTIVO", etiqueta: ETIQUETAS_DE_TIPO.RESUMEN_EJECUTIVO },
];

function tonoDeEstado(estado: Reporte["estado"]): EstadoDeBadge {
  if (estado === "LISTO") {
    return "ok";
  }
  return estado === "FALLIDO" ? "error" : "pendiente";
}

export function GeneradorDeReportes({
  inicial,
  periodo,
  puedeGenerar,
}: PropsDeGeneradorDeReportes): JSX.Element {
  const [reportes, setReportes] = useState<readonly Reporte[]>(inicial);
  const [tipo, setTipo] = useState<TipoReporte>("FACTURACION");
  const [formato, setFormato] = useState<FormatoReporte>("CSV");
  const [rango, setRango] = useState<RangoDePeriodo>(periodo);
  const [estimacion, setEstimacion] = useState<Previsualizacion | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [generando, setGenerando] = useState(false);

  const formatos = FORMATOS_POR_TIPO[tipo];

  async function estimar(
    siguienteTipo: TipoReporte,
    siguienteRango: RangoDePeriodo,
  ): Promise<void> {
    setError(null);
    try {
      setEstimacion(await previsualizar(siguienteTipo, siguienteRango));
    } catch (fallo) {
      setEstimacion(null);
      setError(
        fallo instanceof ErrorDeReporte ? fallo.message : "No se pudo previsualizar el reporte.",
      );
    }
  }

  function cambiarTipo(valor: string): void {
    const siguiente = valor as TipoReporte;
    setTipo(siguiente);
    // El formato elegido puede no existir para el tipo nuevo: se cae al primero que sí.
    const admitidos = FORMATOS_POR_TIPO[siguiente];
    if (!admitidos.includes(formato)) {
      setFormato(admitidos[0] as FormatoReporte);
    }
    void estimar(siguiente, rango);
  }

  function cambiarRango(cambios: RangoDePeriodo): void {
    const siguiente = { ...rango, ...cambios };
    setRango(siguiente);
    void estimar(tipo, siguiente);
  }

  async function generar(): Promise<void> {
    setGenerando(true);
    setError(null);
    try {
      await generarReporte(tipo, formato, rango);
      setReportes((await listarReportes()).reportes);
    } catch (fallo) {
      setError(fallo instanceof ErrorDeReporte ? fallo.message : "No se pudo generar el reporte.");
    } finally {
      setGenerando(false);
    }
  }

  const columnas: readonly Columna<Reporte>[] = [
    { clave: "tipo", titulo: "Tipo", celda: (fila) => ETIQUETAS_DE_TIPO[fila.tipo] },
    { clave: "formato", titulo: "Formato", celda: (fila) => fila.formato },
    { clave: "periodo", titulo: "Período", celda: (fila) => `${fila.desde} a ${fila.hasta}` },
    {
      clave: "estado",
      titulo: "Estado",
      celda: (fila) => <Badge estado={tonoDeEstado(fila.estado)}>{fila.estado}</Badge>,
    },
    {
      clave: "archivo",
      titulo: "Archivo",
      alDerecha: true,
      celda: (fila) =>
        fila.descargable ? (
          <a href={urlDeReporte(fila.id)} download>
            Descargar
          </a>
        ) : (
          "—"
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

      {puedeGenerar && (
        <Card titulo="Generar un reporte">
          <div className="rep-filtros">
            <Select
              id="rep-tipo"
              etiqueta="Tipo"
              opciones={TIPOS.map((uno) => ({ valor: uno.valor, etiqueta: uno.etiqueta }))}
              value={tipo}
              onChange={(evento) => cambiarTipo(evento.target.value)}
            />
            <Select
              id="rep-formato"
              etiqueta="Formato"
              opciones={formatos.map((uno) => ({ valor: uno, etiqueta: uno }))}
              value={formato}
              onChange={(evento) => setFormato(evento.target.value as FormatoReporte)}
            />
            <Campo
              id="rep-gen-desde"
              etiqueta="Desde"
              type="date"
              value={rango.desde ?? ""}
              onChange={(evento) => cambiarRango({ desde: evento.target.value })}
            />
            <Campo
              id="rep-gen-hasta"
              etiqueta="Hasta"
              type="date"
              value={rango.hasta ?? ""}
              onChange={(evento) => cambiarRango({ hasta: evento.target.value })}
            />
          </div>

          {estimacion !== null && (
            <p className="rep-previsualizacion">
              {estimacion.hay_datos
                ? `Se van a exportar ${estimacion.cantidad} registros por $ ${estimacion.total}.`
                : "El período seleccionado no tiene datos para este tipo de reporte."}
            </p>
          )}

          <Button onClick={() => void generar()} cargando={generando}>
            Generar
          </Button>
        </Card>
      )}

      <Card titulo="Reportes generados">
        <Tabla
          titulo="Historial de reportes"
          columnas={columnas}
          filas={reportes}
          claveDeFila={(fila) => fila.id}
          vacia="Todavía no generaste ningún reporte."
        />
      </Card>
    </>
  );
}
