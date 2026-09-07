/**
 * PAN-FAC-02 — Facturación · Detalle (HU-E5-02).
 *
 * Everything RN-02 asks for — número, tipo, fecha, receptor, ítems, total, CAE y su
 * vencimiento — and nothing that could change it. **There is no edit here at all**, and
 * that is RN-01 rather than an omission: an authorised document is immutable, and a form
 * that let somebody try would be a form whose Save button can only fail.
 *
 * **The download is offered only for an authorised document** and the rejection message is
 * shown instead when there is one — ARCA's own code and words, because the story asks for
 * «Error 10016: …» verbatim and paraphrasing forty numeric codes is how one of them ends up
 * meaning the wrong thing in a message somebody takes to their accountant.
 */

"use client";

import {
  Alert,
  Badge,
  Button,
  Card,
  Tabla,
  formatearFecha,
  formatearFechaHora,
  formatearNumero,
} from "@/shared";
import type { Columna } from "@/shared";

import { ETIQUETAS_DE_ESTADO, numeroFormateado, tonoDeEstado } from "../api/comprobante";
import type { Comprobante, ItemDeComprobante } from "../api/comprobante";
import { ETIQUETAS_DE_TIPO } from "../api/puntoDeVenta";

export interface PropsDeDetalleDeComprobante {
  readonly comprobante: Comprobante;
  /** The point of sale's own number, for the `0001-00000123` form ARCA prints. */
  readonly puntoNumero: number | null;
}

const COLUMNAS: readonly Columna<ItemDeComprobante>[] = [
  { clave: "descripcion", titulo: "Descripcion", celda: (fila) => fila.descripcion },
  {
    clave: "cantidad",
    titulo: "Cantidad",
    celda: (fila) => formatearNumero(fila.cantidad, undefined, 2),
    alDerecha: true,
  },
  {
    clave: "precio",
    titulo: "Precio unitario",
    celda: (fila) => `$ ${formatearNumero(fila.precio_unitario)}`,
    alDerecha: true,
  },
  {
    clave: "iva",
    titulo: "IVA",
    // The rate as a percentage, computed for **display only**. Multiplying by 100 is not
    // business logic: the amount it applies to arrived already calculated.
    celda: (fila) => `${formatearNumero(String(Number(fila.alicuota_iva) * 100), undefined, 1)}%`,
    alDerecha: true,
  },
  {
    clave: "subtotal",
    titulo: "Subtotal",
    celda: (fila) => `$ ${formatearNumero(fila.subtotal)}`,
    alDerecha: true,
  },
];

export function DetalleDeComprobante({
  comprobante,
  puntoNumero,
}: PropsDeDetalleDeComprobante): JSX.Element {
  return (
    <>
      {comprobante.motivo_de_rechazo !== null && (
        // ARCA's own words. See the module docstring on why they are not translated.
        <Alert tono="error" titulo="ARCA rechazó el comprobante">
          {comprobante.motivo_de_rechazo}
        </Alert>
      )}

      {comprobante.estado === "ENVIADO_A_ARCA" && (
        <Alert tono="neutral" titulo="Esperando la respuesta de ARCA">
          El comprobante ya salió. Cuando ARCA conteste, acá vas a ver el CAE o el motivo del
          rechazo. No lo emitas de nuevo: si ARCA lo autorizó, un segundo intento sería un segundo
          comprobante por la misma venta.
        </Alert>
      )}

      <div className="fac-detalle">
        <Card titulo="Comprobante">
          <dl className="fac-datos">
            <dt>Número</dt>
            <dd className="fac-mono">{numeroFormateado(comprobante, puntoNumero)}</dd>
            <dt>Tipo</dt>
            <dd>{ETIQUETAS_DE_TIPO[comprobante.tipo]}</dd>
            <dt>Estado</dt>
            <dd>
              <Badge estado={tonoDeEstado(comprobante.estado)}>
                {ETIQUETAS_DE_ESTADO[comprobante.estado]}
              </Badge>
            </dd>
            <dt>Fecha de emisión</dt>
            <dd>{formatearFechaHora(comprobante.fecha_emision)}</dd>
            <dt>CAE</dt>
            <dd className="fac-mono">{comprobante.cae ?? "—"}</dd>
            <dt>Vencimiento del CAE</dt>
            <dd>{formatearFecha(comprobante.cae_vence_el)}</dd>
          </dl>
        </Card>

        <Card titulo="Receptor">
          <dl className="fac-datos">
            <dt>Razón social</dt>
            <dd>{comprobante.receptor_nombre}</dd>
            <dt>CUIT</dt>
            <dd className="fac-mono">{comprobante.receptor_cuit}</dd>
            <dt>Condición de IVA</dt>
            <dd>{comprobante.receptor_condicion_iva.replaceAll("_", " ").toLowerCase()}</dd>
            <dt>Saldo pendiente</dt>
            <dd>$ {formatearNumero(comprobante.saldo_pendiente)}</dd>
          </dl>
        </Card>
      </div>

      <Tabla
        titulo="Detalle"
        columnas={COLUMNAS}
        filas={comprobante.items}
        claveDeFila={(fila) => fila.id}
        vacia="Este comprobante no tiene items."
      />

      <div className="fac-totales">
        <span>Subtotal: $ {formatearNumero(comprobante.subtotal)}</span>
        <span>IVA: $ {formatearNumero(comprobante.total_iva)}</span>
        <span className="fac-totales__final">Total: $ {formatearNumero(comprobante.total)}</span>
      </div>

      {comprobante.descargable && (
        <div className="fac-acciones">
          <Button
            onClick={() => {
              window.open(`/api/comprobantes/${comprobante.id}/pdf`, "_blank");
            }}
          >
            Descargar PDF
          </Button>
        </div>
      )}
    </>
  );
}
