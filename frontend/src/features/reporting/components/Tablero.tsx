/**
 * PAN-REP-01 — Reportería · Tablero (HU-E10-01).
 *
 * Las seis cifras del período, la distribución por tipo de comprobante, el facturado por
 * semana y las dos visualizaciones de cobranza (cobrado por semana y cobros por estado), todo
 * del rango que el selector elige.
 *
 * **Nada acá calcula nada.** Ni la variación, ni el neto, ni el total por semana: llegan
 * calculados del backend, donde son reglas de negocio (RN-02 y RN-03). Recalcularlos en el
 * navegador haría que el mismo mes diera un número en el panel y otro en el resumen ejecutivo
 * que se le manda al contador.
 *
 * **Una sola grilla de tarjetas, y no tres.** Lo facturado, lo cobrado, lo pendiente, lo en
 * mora, los turnos y las operaciones son seis respuestas a la misma pregunta —«cómo le fue al
 * negocio en este período»— y se leen en una sola pasada si tienen el mismo tamaño, el mismo
 * ritmo y el mismo tratamiento que las del tablero de inicio. Repartidas en tres cajas de
 * tamaños distintos, el ojo asume una jerarquía que los datos no tienen.
 *
 * **Un guion no es un cero.** Cuando el período anterior fue cero no hay con qué comparar, y
 * la variación llega en `null`: mostrar «0%» le diría a alguien que su negocio no creció
 * cuando la verdad es que el mes pasado no existía. Lo pendiente y lo en mora, en cambio, no
 * llevan variación **ninguna**: son un saldo a hoy, no un flujo del período, y no hay período
 * anterior contra el cual medirlos ni siquiera en principio.
 */

"use client";

import { useState } from "react";

import { ETIQUETAS_DE_ESTADO } from "@/features/payments";
import { Alert, formatearNumero } from "@/shared";

import {
  ErrorDeReporte,
  MENSAJE_SIN_ACTIVIDAD,
  etiquetaDeSemana,
  nombreDeSemana,
  nombreDeTipoDeComprobante,
  textoDePeriodo,
  verTablero,
} from "../api/reporte";
import type { Metrica, RangoDePeriodo, Tablero as TableroDatos } from "../api/reporte";
import { Cifra } from "./Cifras";
import { BarrasPorSemana, Distribucion } from "./Graficos";
import { SelectorDePeriodo } from "./SelectorDePeriodo";
import {
  IconoAlerta,
  IconoCalendario,
  IconoDocumento,
  IconoLista,
  IconoReloj,
  IconoTarjeta,
} from "./Iconos";

export interface PropsDeTablero {
  readonly inicial: TableroDatos;
}

/** Un importe del backend, listo para mostrar. Nunca se opera con él. */
function pesos(valor: string): string {
  return `$ ${formatearNumero(valor)}`;
}

/** Un conteo: con separador de miles y sin decimales, que los turnos no vienen en centavos. */
function cantidad(valor: string): string {
  return formatearNumero(valor, undefined, 0);
}

function pieDeMoneda(metrica: Metrica): string {
  return `Período anterior · ${pesos(metrica.anterior)}`;
}

function pieDeCantidad(metrica: Metrica): string {
  return `Período anterior · ${cantidad(metrica.anterior)}`;
}

/** «Pagado» y «En mora» son de payments; un estado que todavía no conoce se muestra tal cual. */
function nombreDeEstado(estado: string): string {
  const etiquetas: Readonly<Record<string, string>> = ETIQUETAS_DE_ESTADO;
  return etiquetas[estado] ?? estado;
}

function cantidadDeCobros(cuantos: number | undefined): string {
  const n = cuantos ?? 0;
  return n === 1 ? "1 cobro" : `${formatearNumero(String(n), undefined, 0)} cobros`;
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

  // Sólo se reacomoda: el monto de cada estado llega del backend, no se suma ni se recalcula.
  const montosPorEstado = Object.fromEntries(
    Object.entries(tablero.cobros_por_estado).map(([estado, cobros]) => [estado, cobros.monto]),
  );

  return (
    <>
      {error !== null && (
        <Alert tono="error" titulo="No se pudo completar">
          {error}
        </Alert>
      )}

      <SelectorDePeriodo
        rango={rango}
        resumen={textoDePeriodo(tablero.desde, tablero.hasta)}
        alCambiar={(cambios) => void aplicar(cambios)}
      />

      {tablero.sin_actividad ? (
        <Alert tono="neutral" titulo="Sin actividad">
          {MENSAJE_SIN_ACTIVIDAD}
        </Alert>
      ) : null}

      <div className="rep-kpis">
        <Cifra
          titulo="Facturado"
          valor={pesos(tablero.facturado.valor)}
          pie={pieDeMoneda(tablero.facturado)}
          icono={<IconoDocumento />}
          tono="menta"
          variacion={tablero.facturado.variacion}
        />
        <Cifra
          titulo="Cobrado"
          valor={pesos(tablero.cobrado.valor)}
          pie={pieDeMoneda(tablero.cobrado)}
          icono={<IconoTarjeta />}
          tono="menta"
          variacion={tablero.cobrado.variacion}
        />
        <Cifra
          titulo="Pendiente de cobro"
          valor={pesos(tablero.pendiente)}
          pie="Emitido y todavía sin cobrar"
          icono={<IconoReloj />}
          tono="ambar"
        />
        <Cifra
          titulo="En mora"
          valor={pesos(tablero.en_mora)}
          pie="Vencido y sin cobrar"
          icono={<IconoAlerta />}
          tono="ambar"
        />
        <Cifra
          titulo="Turnos gestionados"
          valor={cantidad(tablero.turnos.valor)}
          pie={pieDeCantidad(tablero.turnos)}
          icono={<IconoCalendario />}
          tono="tinta"
          variacion={tablero.turnos.variacion}
        />
        <Cifra
          titulo="Operaciones"
          valor={cantidad(tablero.operaciones.valor)}
          pie={pieDeCantidad(tablero.operaciones)}
          icono={<IconoLista />}
          tono="tinta"
          variacion={tablero.operaciones.variacion}
        />
      </div>

      <div className="rep-graficos">
        <section className="rep-panel">
          <div className="rep-panel__head">
            <div>
              <h2 className="rep-panel__titulo">Facturación por semana</h2>
              <p className="rep-panel__sub">Lo emitido en cada semana del período</p>
            </div>
          </div>
          <BarrasPorSemana
            datos={tablero.por_semana}
            vacio="No hubo facturación en este período."
            nombrar={etiquetaDeSemana}
            detallar={nombreDeSemana}
            notaUnica="Es la única semana con facturación del período: no hay otra contra la cual medirla."
          />
        </section>

        <section className="rep-panel">
          <div className="rep-panel__head">
            <div>
              <h2 className="rep-panel__titulo">Distribución por tipo de comprobante</h2>
              <p className="rep-panel__sub">Qué parte de lo facturado aportó cada tipo</p>
            </div>
          </div>
          <Distribucion
            datos={tablero.por_tipo}
            vacio="No se emitieron comprobantes en este período."
            nombrar={nombreDeTipoDeComprobante}
            notaUnica="Es el único tipo que se emitió: el 100 % de lo facturado en el período."
          />
        </section>

        <section className="rep-panel">
          <div className="rep-panel__head">
            <div>
              <h2 className="rep-panel__titulo">Cobrado por semana</h2>
              <p className="rep-panel__sub">
                Lo cobrado en cada semana, por fecha de pago, menos lo devuelto
              </p>
            </div>
          </div>
          <BarrasPorSemana
            datos={tablero.cobrado_por_semana}
            vacio="No hubo cobros en este período."
            nombrar={etiquetaDeSemana}
            detallar={nombreDeSemana}
            notaUnica="Es la única semana con cobros del período: no hay otra contra la cual medirla."
          />
        </section>

        <section className="rep-panel">
          <div className="rep-panel__head">
            <div>
              <h2 className="rep-panel__titulo">Cobros por estado</h2>
              <p className="rep-panel__sub">
                Cobros creados en el período, por su estado actual · tasa de cobro{" "}
                {formatearNumero(tablero.tasa_de_cobro)} %
              </p>
            </div>
          </div>
          <Distribucion
            datos={montosPorEstado}
            vacio="No se crearon cobros en este período."
            nombrar={nombreDeEstado}
            secundario={(estado) => cantidadDeCobros(tablero.cobros_por_estado[estado]?.cantidad)}
            notaUnica="Es el único estado de los cobros creados en el período: el 100 % de lo creado."
          />
        </section>
      </div>
    </>
  );
}
