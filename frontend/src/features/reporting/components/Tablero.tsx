/**
 * PAN-REP-01 — Reportería · Tablero (HU-E10-01).
 *
 * Las cuatro métricas del encabezado con su variación, la distribución por tipo de
 * comprobante y el facturado por semana, todo del período que el selector elige.
 *
 * **Nada acá calcula nada.** Ni la variación, ni el neto, ni el total por semana: llegan
 * calculados del backend, donde son reglas de negocio (RN-02 y RN-03). Recalcularlos en el
 * navegador haría que el mismo mes diera un número en el panel y otro en el resumen ejecutivo
 * que se le manda al contador.
 *
 * **Un guion no es un cero.** Cuando el período anterior fue cero no hay con qué comparar, y
 * la variación llega en `null`: mostrar «0%» le diría a alguien que su negocio no creció
 * cuando la verdad es que el mes pasado no existía.
 *
 * **El gráfico son barras hechas con divs.** No hay librería de gráficos en este repositorio y
 * este épico no la introduce: cuatro o cinco barras con su valor al lado se leen igual, pesan
 * cero y funcionan sin JavaScript una vez renderizadas.
 */

"use client";

import { useState } from "react";

import { Alert, Campo, Card, formatearNumero } from "@/shared";

import { ErrorDeReporte, MENSAJE_SIN_ACTIVIDAD, verTablero } from "../api/reporte";
import type { Metrica, RangoDePeriodo, Tablero as TableroDatos } from "../api/reporte";

export interface PropsDeTablero {
  readonly inicial: TableroDatos;
}

/** Lo que el gráfico dibuja como alto máximo de una barra, en porcentaje. */
const ALTO_MAXIMO = 100;

function mayorDe(valores: readonly string[]): number {
  const numeros = valores.map((uno) => Math.abs(Number(uno)));
  const mayor = Math.max(0, ...numeros);
  return mayor === 0 ? 1 : mayor;
}

function Variacion({ metrica }: { readonly metrica: Metrica }): JSX.Element {
  if (metrica.variacion === null) {
    return (
      <span className="rep-variacion" title="No hay período anterior con el que comparar">
        —
      </span>
    );
  }
  const sube = Number(metrica.variacion) >= 0;
  return (
    <span
      className={sube ? "rep-variacion rep-variacion--sube" : "rep-variacion rep-variacion--baja"}
    >
      {sube ? "▲" : "▼"} {metrica.variacion}%
    </span>
  );
}

function Numero({
  titulo,
  metrica,
  moneda = true,
}: {
  readonly titulo: string;
  readonly metrica: Metrica;
  readonly moneda?: boolean;
}): JSX.Element {
  return (
    <Card titulo={titulo}>
      <p className="fac-totales__final">
        {moneda ? `$ ${formatearNumero(metrica.valor)}` : metrica.valor}
      </p>
      <p className="rep-comparacion">
        <Variacion metrica={metrica} /> vs. período anterior
      </p>
    </Card>
  );
}

function Barras({
  titulo,
  datos,
  vacio,
}: {
  readonly titulo: string;
  readonly datos: Readonly<Record<string, string>>;
  readonly vacio: string;
}): JSX.Element {
  const entradas = Object.entries(datos);
  if (entradas.length === 0) {
    return (
      <Card titulo={titulo}>
        <p className="tabla__vacia">{vacio}</p>
      </Card>
    );
  }
  const tope = mayorDe(entradas.map(([, valor]) => valor));

  return (
    <Card titulo={titulo}>
      <ul className="rep-barras">
        {entradas.map(([clave, valor]) => (
          <li key={clave} className="rep-barras__fila">
            <span className="rep-barras__clave">{clave}</span>
            <span className="rep-barras__pista">
              <span
                className="rep-barras__barra"
                style={{ width: `${(Math.abs(Number(valor)) / tope) * ALTO_MAXIMO}%` }}
              />
            </span>
            <span className="rep-barras__valor">$ {formatearNumero(valor)}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function Tablero({ inicial }: PropsDeTablero): JSX.Element {
  const [tablero, setTablero] = useState<TableroDatos>(inicial);
  const [rango, setRango] = useState<RangoDePeriodo>({
    desde: inicial.desde,
    hasta: inicial.hasta,
  });
  const [error, setError] = useState<string | null>(null);

  async function aplicar(cambios: RangoDePeriodo): Promise<void> {
    const siguiente = { ...rango, ...cambios };
    setRango(siguiente);
    if (siguiente.desde === undefined || siguiente.hasta === undefined) {
      return;
    }
    setError(null);
    try {
      setTablero(await verTablero(siguiente));
    } catch (fallo) {
      setError(
        fallo instanceof ErrorDeReporte ? fallo.message : "No se pudo actualizar el tablero.",
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

      <div className="rep-filtros">
        <Campo
          id="rep-desde"
          etiqueta="Desde"
          type="date"
          value={rango.desde ?? ""}
          onChange={(evento) => void aplicar({ desde: evento.target.value })}
        />
        <Campo
          id="rep-hasta"
          etiqueta="Hasta"
          type="date"
          value={rango.hasta ?? ""}
          onChange={(evento) => void aplicar({ hasta: evento.target.value })}
        />
      </div>

      {tablero.sin_actividad ? (
        <Alert tono="neutral" titulo="Sin actividad">
          {MENSAJE_SIN_ACTIVIDAD}
        </Alert>
      ) : null}

      <div className="fac-detalle">
        <Numero titulo="Facturado" metrica={tablero.facturado} />
        <Numero titulo="Cobrado" metrica={tablero.cobrado} />
        <Numero titulo="Turnos gestionados" metrica={tablero.turnos} moneda={false} />
        <Numero titulo="Operaciones" metrica={tablero.operaciones} moneda={false} />
      </div>

      <div className="fac-detalle">
        <Card titulo="Pendiente de cobro">
          <p className="fac-totales__final">$ {formatearNumero(tablero.pendiente)}</p>
        </Card>
        <Card titulo="En mora">
          <p className="fac-totales__final">$ {formatearNumero(tablero.en_mora)}</p>
        </Card>
      </div>

      <Barras
        titulo="Facturación por semana"
        datos={tablero.por_semana}
        vacio="No hubo facturación en este período."
      />
      <Barras
        titulo="Distribución por tipo de comprobante"
        datos={tablero.por_tipo}
        vacio="No se emitieron comprobantes en este período."
      />
    </>
  );
}
