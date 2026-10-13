/**
 * La franja de cifras de arriba de PAN-ING-01.
 *
 * Cuatro números que se leen de un vistazo antes de bajar: cuántas planillas hay, cuántas cargas
 * se hicieron y cómo les fue. **Son sumas de lo que la pantalla ya tiene** —los vínculos y las
 * cargas recientes—; no se pide nada nuevo al backend ni se calcula nada de negocio acá.
 */

import type { Carga, Vinculo } from "../api/planilla";
import { Icono } from "./iconos";
import type { NombreDeIcono } from "./iconos";

export interface CifrasDeIngesta {
  readonly planillas: number;
  readonly conMapeo: number;
  readonly cargas: number;
  readonly filasImportadas: number;
  readonly filasConError: number;
}

export function cifrasDeIngesta(
  vinculos: readonly Vinculo[],
  cargas: readonly Carga[],
): CifrasDeIngesta {
  return {
    planillas: vinculos.length,
    conMapeo: vinculos.filter((vinculo) => vinculo.tiene_mapeo).length,
    cargas: cargas.length,
    filasImportadas: cargas.reduce((suma, carga) => suma + carga.filas_ok, 0),
    filasConError: cargas.reduce((suma, carga) => suma + carga.filas_error, 0),
  };
}

interface Tarjeta {
  readonly clave: string;
  readonly icono: NombreDeIcono;
  readonly etiqueta: string;
  readonly valor: number;
  readonly nota: string;
  readonly tono: "" | "ok" | "error";
}

function tarjetasDe(cifras: CifrasDeIngesta): readonly Tarjeta[] {
  return [
    {
      clave: "planillas",
      icono: "planilla",
      etiqueta: "Planillas",
      valor: cifras.planillas,
      nota: `${cifras.conMapeo} con mapeo`,
      tono: "",
    },
    {
      clave: "cargas",
      icono: "historial",
      etiqueta: "Cargas",
      valor: cifras.cargas,
      nota: "Las más recientes",
      tono: "",
    },
    {
      clave: "importadas",
      icono: "base",
      etiqueta: "Filas importadas",
      valor: cifras.filasImportadas,
      nota: "En las cargas recientes",
      tono: cifras.filasImportadas > 0 ? "ok" : "",
    },
    {
      clave: "errores",
      icono: "alerta",
      etiqueta: "Filas con error",
      valor: cifras.filasConError,
      nota: cifras.filasConError > 0 ? "Para revisar" : "Todo en orden",
      tono: cifras.filasConError > 0 ? "error" : "",
    },
  ];
}

export function ResumenDeIngesta({ cifras }: { readonly cifras: CifrasDeIngesta }): JSX.Element {
  return (
    <ul className="ing-kpis" aria-label="Resumen de la ingesta">
      {tarjetasDe(cifras).map((tarjeta) => (
        <li key={tarjeta.clave} className={`ing-kpi ing-kpi--${tarjeta.tono || "neutro"}`}>
          <span className="ing-kpi__ico">
            <Icono nombre={tarjeta.icono} />
          </span>
          <span className="ing-kpi__cuerpo">
            <span className="ing-kpi__etiqueta">{tarjeta.etiqueta}</span>
            <b className="ing-kpi__valor" data-clave={tarjeta.clave}>
              {tarjeta.valor.toLocaleString("es-AR")}
            </b>
            <span className="ing-kpi__nota">{tarjeta.nota}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}
