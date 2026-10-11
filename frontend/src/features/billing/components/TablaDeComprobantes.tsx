/**
 * La tabla del listado de comprobantes.
 *
 * **Toda la fila abre el comprobante, sin un solo manejador de clic.** El número es un enlace
 * real (`<a>`: se abre en otra pestaña, se copia, responde a Enter) y su `::after` se estira
 * sobre la fila entera; los enlaces de acción van por encima con `z-index`, así que un clic en
 * ellos no navega a la fila. Es el patrón del «enlace estirado»: el teclado y el lector de
 * pantalla ven un enlace por fila, no una fila con un clic escondido.
 *
 * Los importes salen como texto de la API: sólo se les da formato para mostrarlos.
 */

import { ArrowRight, Ban, Download } from "lucide-react";
import Link from "next/link";
import type { CSSProperties } from "react";

import { Badge, formatearFecha, formatearNumero } from "@/shared";

import { ETIQUETAS_DE_ESTADO, tonoDeEstado } from "../api/comprobante";
import type { Comprobante, EstadoComprobante } from "../api/comprobante";
import { ETIQUETAS_DE_TIPO } from "../api/puntoDeVenta";
import { AvatarDeReceptor } from "./AvatarDeReceptor";

export interface PropsDeTablaDeComprobantes {
  readonly filas: readonly Comprobante[];
  readonly puedeEmitir: boolean;
}

function numeroDe(fila: Comprobante): string {
  return fila.numero === null ? "Sin numerar" : String(fila.numero).padStart(8, "0");
}

/** La misma regla que el detalle: sólo una factura autorizada se anula con nota de crédito. */
function sePuedeAnular(fila: Comprobante, puedeEmitir: boolean): boolean {
  return puedeEmitir && fila.estado === "AUTORIZADO" && !fila.tipo.startsWith("NOTA_CREDITO");
}

function Fila({
  fila,
  indice,
  puedeEmitir,
}: {
  readonly fila: Comprobante;
  readonly indice: number;
  readonly puedeEmitir: boolean;
}): JSX.Element {
  const numero = numeroDe(fila);
  return (
    <tr
      className={`fac-lst-fila${fila.estado === "ANULADO" ? " fac-lst-fila--anulada" : ""}`}
      style={{ "--fac-i": Math.min(indice, 12) } as CSSProperties}
    >
      <td>
        <div className="fac-lst-numero">
          <Link href={`/facturacion/${fila.id}`} className="fac-lst-enlace">
            {numero}
          </Link>
          <span className="fac-lst-tipo">{ETIQUETAS_DE_TIPO[fila.tipo]}</span>
        </div>
      </td>
      <td>
        <div className="fac-lst-cliente">
          <AvatarDeReceptor nombre={fila.receptor_nombre} />
          <span className="fac-lst-cliente__nombre">{fila.receptor_nombre}</span>
        </div>
      </td>
      <td className="tabla__celda--derecha">
        {/* Interpolado entero: un salto de línea no se lleva el espacio tras el signo. */}
        <span className="fac-lst-importe">{`$ ${formatearNumero(fila.total)}`}</span>
      </td>
      <td className="fac-lst-col-fecha">
        <span className="fac-lst-fecha">
          {formatearFecha(fila.fecha_emision ?? fila.created_at)}
        </span>
      </td>
      <td>
        <Badge estado={tonoDeEstado(fila.estado)}>
          {ETIQUETAS_DE_ESTADO[fila.estado as EstadoComprobante]}
        </Badge>
      </td>
      <td className="fac-lst-col-acciones">
        <span className="fac-lst-acciones">
          {fila.descargable && (
            <a
              className="fac-lst-accion"
              href={`/api/comprobantes/${fila.id}/pdf`}
              target="_blank"
              rel="noreferrer"
              aria-label={`Descargar PDF del comprobante ${numero}`}
              title="Descargar PDF"
            >
              <Download aria-hidden="true" size={16} />
            </a>
          )}
          {sePuedeAnular(fila, puedeEmitir) && (
            <Link
              className="fac-lst-accion fac-lst-accion--baja"
              href={`/facturacion/${fila.id}/anular`}
              aria-label={`Anular el comprobante ${numero}`}
              title="Anular con nota de crédito"
            >
              <Ban aria-hidden="true" size={16} />
            </Link>
          )}
          <span className="fac-lst-ir" aria-hidden="true">
            Ver
            <ArrowRight size={14} />
          </span>
        </span>
      </td>
    </tr>
  );
}

export function TablaDeComprobantes({
  filas,
  puedeEmitir,
}: PropsDeTablaDeComprobantes): JSX.Element {
  return (
    <div className="tabla__contenedor">
      <table className="tabla fac-lst-tabla">
        <caption className="tabla__caption">Comprobantes emitidos</caption>
        <thead>
          <tr>
            <th scope="col">Número</th>
            <th scope="col">Cliente</th>
            <th scope="col" className="tabla__celda--derecha">
              Total
            </th>
            <th scope="col" className="fac-lst-col-fecha">
              Fecha
            </th>
            <th scope="col">Estado</th>
            <th scope="col" className="fac-lst-col-acciones">
              <span className="solo-lectores">Acciones</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {filas.map((fila, indice) => (
            <Fila key={fila.id} fila={fila} indice={indice} puedeEmitir={puedeEmitir} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
