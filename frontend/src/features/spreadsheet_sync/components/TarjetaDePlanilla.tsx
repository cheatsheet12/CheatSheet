/**
 * Una planilla vinculada, dibujada como tarjeta (PAN-ING-01).
 *
 * Antes eran filas de una tabla con cinco columnas; una planilla tiene un nombre, un origen, un
 * estado y un camino por recorrer (subir, mapear, leer), y eso se lee mejor como una unidad que
 * como celdas sueltas. La tarjeta lo dice de arriba abajo: qué es, en qué paso está y qué sigue.
 *
 * **Los pasos se derivan, no se piden.** `tiene_mapeo` y `ultima_lectura` ya llegan en el
 * `Vinculo`; el avance es una lectura de esos dos datos y no lógica de negocio nueva.
 */

import Link from "next/link";

import { Badge, Button, formatearFecha } from "@/shared";
import type { EstadoDeBadge } from "@/shared";

import { ETIQUETAS_DE_PROVEEDOR } from "../api/planilla";
import type { Vinculo } from "../api/planilla";
import { Icono } from "./iconos";

export type SituacionDePaso = "hecho" | "actual" | "pendiente";

export interface PasoDePlanilla {
  readonly clave: "subida" | "mapeo" | "lectura";
  readonly titulo: string;
  readonly detalle: string;
  readonly situacion: SituacionDePaso;
}

/** What a link's state is called on screen, and how the badge is toned. */
export function estadoDe(vinculo: Vinculo): {
  readonly texto: string;
  readonly tono: EstadoDeBadge;
} {
  if (vinculo.pausado) {
    return { texto: "Pausada", tono: "atencion" };
  }
  if (!vinculo.tiene_mapeo) {
    return { texto: "Falta mapear", tono: "atencion" };
  }
  return { texto: "Vinculada", tono: "ok" };
}

export function tamanoLegible(bytes: number | null): string {
  if (bytes === null) {
    return "—";
  }
  const mb = bytes / (1024 * 1024);
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/**
 * Los tres pasos de una planilla: conexión, mapeo y lectura.
 *
 * El primero siempre está hecho —la planilla existe—; el segundo lo marca `tiene_mapeo`; el
 * tercero, `ultima_lectura`. El primero que falta es el «actual», que es el que la tarjeta
 * resalta y el que decide qué acción lleva relieve.
 */
export function pasosDeLaPlanilla(vinculo: Vinculo): readonly PasoDePlanilla[] {
  const leida = vinculo.ultima_lectura !== null;
  const hechos = [true, vinculo.tiene_mapeo, leida];
  const actual = hechos.indexOf(false);
  const situacion = (indice: number): SituacionDePaso =>
    hechos[indice] ? "hecho" : indice === actual ? "actual" : "pendiente";

  return [
    {
      clave: "subida",
      titulo: vinculo.proveedor === "ARCHIVO" ? "Subida" : "Conexión",
      detalle: "Lista",
      situacion: situacion(0),
    },
    {
      clave: "mapeo",
      titulo: "Mapeo",
      detalle: vinculo.tiene_mapeo ? "Propuesto" : "Pendiente",
      situacion: situacion(1),
    },
    {
      clave: "lectura",
      titulo: "Lectura",
      detalle:
        vinculo.ultima_lectura === null ? "Sin leer" : formatearFecha(vinculo.ultima_lectura),
      situacion: situacion(2),
    },
  ];
}

export interface PropsDeTarjetaDePlanilla {
  readonly vinculo: Vinculo;
  readonly puedeEditar: boolean;
  readonly alProcesar: (vinculo: Vinculo) => void;
  readonly alDesvincular: (vinculo: Vinculo) => void;
}

function Progreso({ pasos }: { readonly pasos: readonly PasoDePlanilla[] }): JSX.Element {
  return (
    <ol className="ing-plan__pasos" aria-label="Avance de la planilla">
      {pasos.map((paso, indice) => (
        <li key={paso.clave} className="ing-plan__paso" data-situacion={paso.situacion}>
          <span className="ing-plan__marca">
            {paso.situacion === "hecho" ? <Icono nombre="tilde" /> : indice + 1}
          </span>
          <span className="ing-plan__paso-texto">
            <b>{paso.titulo}</b>
            <span>{paso.detalle}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}

export function TarjetaDePlanilla({
  vinculo,
  puedeEditar,
  alProcesar,
  alDesvincular,
}: PropsDeTarjetaDePlanilla): JSX.Element {
  const { texto, tono } = estadoDe(vinculo);
  const nombre = vinculo.nombre_archivo ?? vinculo.identificador_externo ?? vinculo.hoja_empresa;

  return (
    <li className="ing-plan">
      <div className="ing-plan__cabecera">
        <span className="ing-plan__ico">
          <Icono nombre="planilla" />
        </span>
        <div className="ing-plan__datos">
          <h3 className="ing-plan__nombre">{nombre}</h3>
          <p className="ing-plan__meta">
            <span>{ETIQUETAS_DE_PROVEEDOR[vinculo.proveedor]}</span>
            <span>{tamanoLegible(vinculo.tamano_bytes)}</span>
            {/* HU-E3-07's fourth criterion: a link that cannot be written back to says so,
                rather than offering an option that would silently do nothing. */}
            <span>{vinculo.escribe_de_vuelta ? "Lectura y escritura" : "Solo lectura"}</span>
          </p>
        </div>
        <Badge estado={tono}>{texto}</Badge>
      </div>

      <Progreso pasos={pasosDeLaPlanilla(vinculo)} />

      {puedeEditar && (
        <div className="ing-acciones-fila">
          {/* «Revisar mapeo» se ofrece **siempre**, y no sólo cuando falta el mapeo, porque
              `tiene_mapeo` dice que hay uno, no que esté confirmado. Un mapeo propuesto y sin
              confirmar no se puede procesar —el caso de uso lo rechaza— y esconder el enlace
              justo ahí dejaría la tarjeta sin ninguna salida hacia adelante. */}
          {vinculo.tiene_mapeo && (
            <Button
              variante="primario"
              onClick={() => {
                alProcesar(vinculo);
              }}
            >
              Procesar
            </Button>
          )}
          {vinculo.proveedor !== "EXCEL_ONLINE" && (
            <Link
              className={vinculo.tiene_mapeo ? "ing-accion" : "ing-accion ing-accion--principal"}
              href={`/ingesta/mapeo/${vinculo.id}`}
            >
              Revisar mapeo
            </Link>
          )}
          <Button
            variante="destructivo"
            confirmacion="Vas a desvincular esta planilla. Los datos que ya se importaron se quedan; solo se corta la conexión."
            onClick={() => {
              alDesvincular(vinculo);
            }}
          >
            <Icono nombre="papelera" />
            Desvincular
          </Button>
        </div>
      )}
    </li>
  );
}
