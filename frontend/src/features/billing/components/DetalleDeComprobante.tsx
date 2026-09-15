/**
 * PAN-FAC-02 — Facturación · Detalle (HU-E5-02).
 *
 * Todo lo que pide RN-02 —número, tipo, fecha, receptor, ítems, total, CAE y su
 * vencimiento— y nada que pueda cambiarlo. **Acá no hay ninguna edición**, y eso es RN-01 y
 * no un olvido: un comprobante autorizado es inmutable, y un formulario que dejara
 * intentarlo sería un formulario cuyo botón Guardar sólo puede fallar.
 *
 * **Que sea inmutable está escrito, no sólo ausente.** La ausencia de un botón «Eliminar»
 * se lee como un olvido; la frase al lado de las acciones se lee como una regla, y es la
 * que explica por qué la única salida es una nota de crédito.
 *
 * **El número, el CAE y el CUIT van en monoespaciada.** Son identificadores fiscales que
 * alguien compara carácter por carácter contra un papel o dicta por teléfono, y en una
 * tipografía proporcional el 1 y la l son el mismo trazo.
 *
 * **La descarga se ofrece sólo para un comprobante autorizado** y en su lugar se muestra el
 * motivo del rechazo cuando lo hay — con el código y las palabras de ARCA, porque la
 * historia pide «Error 10016: …» textual y parafrasear cuarenta códigos numéricos es la
 * forma de que uno termine significando otra cosa en un mensaje que alguien le lleva a su
 * contador.
 */

"use client";

import Link from "next/link";

import {
  Alert,
  Badge,
  Button,
  Tabla,
  formatearFecha,
  formatearFechaHora,
  formatearNumero,
} from "@/shared";
import type { Columna } from "@/shared";

import { ETIQUETAS_DE_ESTADO, numeroFormateado, tonoDeEstado } from "../api/comprobante";
import type { Anulacion, Comprobante, ItemDeComprobante } from "../api/comprobante";
import { ETIQUETAS_DE_TIPO } from "../api/puntoDeVenta";

export interface PropsDeDetalleDeComprobante {
  readonly comprobante: Comprobante;
  /** The point of sale's own number, for the `0001-00000123` form ARCA prints. */
  readonly puntoNumero: number | null;
  /** How much of it has been reversed (HU-E5-04 RN-05). */
  readonly anulacion?: Anulacion | null;
  /** Administrador and Operador reverse; Solo Lectura only looks. */
  readonly puedeAnular?: boolean;
}

const COLUMNAS: readonly Columna<ItemDeComprobante>[] = [
  { clave: "descripcion", titulo: "Descripción", celda: (fila) => fila.descripcion },
  {
    clave: "cantidad",
    titulo: "Cantidad",
    celda: (fila) => (
      <span className="fac-nuevo-importe">{formatearNumero(fila.cantidad, undefined, 2)}</span>
    ),
    alDerecha: true,
  },
  {
    clave: "precio",
    titulo: "Precio unitario",
    celda: (fila) => (
      <span className="fac-nuevo-importe">{`$ ${formatearNumero(fila.precio_unitario)}`}</span>
    ),
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
    celda: (fila) => (
      <span className="fac-nuevo-importe">{`$ ${formatearNumero(fila.subtotal)}`}</span>
    ),
    alDerecha: true,
  },
];

export function DetalleDeComprobante({
  comprobante,
  puntoNumero,
  anulacion = null,
  puedeAnular = false,
}: PropsDeDetalleDeComprobante): JSX.Element {
  return (
    <>
      {/* Los tres avisos juntos y arriba de todo: son lo que cambia qué significa el resto de
          la pantalla, así que se leen antes que el comprobante y no intercalados en él. */}
      <div className="fac-nuevo-avisos">
        {anulacion !== null && Number(anulacion.total_anulado) > 0 && (
          // RN-05. A partial reversal is not a state, it is an amount -- and saying it here
          // is what stops the `AUTORIZADO` badge from reading as "nothing happened to this".
          <Alert
            tono={anulacion.es_total ? "neutral" : "advertencia"}
            titulo={anulacion.es_total ? "Anulado por completo" : "Anulado parcialmente"}
          >
            Se anularon $ {formatearNumero(anulacion.total_anulado)} de ${" "}
            {formatearNumero(anulacion.total_original)}
            {anulacion.es_total
              ? "."
              : `, con $ ${formatearNumero(anulacion.disponible)} vigentes.`}
          </Alert>
        )}

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
      </div>

      {/* El número una sola vez y en grande: es el dato con el que alguien reconoce este
          comprobante, y repetirlo abajo sólo daría dos lugares donde mirar. */}
      <header className="fac-nuevo-documento">
        <div>
          <p className="fac-nuevo-documento__rotulo">Número</p>
          <p className="fac-nuevo-documento__numero">
            {numeroFormateado(comprobante, puntoNumero)}
          </p>
          <p className="fac-nuevo-documento__tipo">{ETIQUETAS_DE_TIPO[comprobante.tipo]}</p>
        </div>
        <div className="fac-nuevo-documento__estado">
          <Badge estado={tonoDeEstado(comprobante.estado)}>
            {ETIQUETAS_DE_ESTADO[comprobante.estado]}
          </Badge>
          <p className="fac-nuevo-documento__fecha">
            Emitido el {formatearFechaHora(comprobante.fecha_emision)}
          </p>
        </div>
      </header>

      <div className="fac-nuevo-columnas">
        <section className="fac-nuevo-tarjeta">
          <p className="fac-nuevo-rotulo">Datos fiscales</p>
          <dl className="fac-nuevo-kv">
            <div className="fac-nuevo-kv__par">
              <dt>CAE</dt>
              <dd className="fac-nuevo-fiscal">{comprobante.cae ?? "—"}</dd>
            </div>
            <div className="fac-nuevo-kv__par">
              <dt>Vencimiento del CAE</dt>
              <dd className="fac-nuevo-fiscal">{formatearFecha(comprobante.cae_vence_el)}</dd>
            </div>
            <div className="fac-nuevo-kv__par">
              <dt>Punto de venta</dt>
              <dd className="fac-nuevo-fiscal">
                {puntoNumero === null ? "—" : String(puntoNumero).padStart(4, "0")}
              </dd>
            </div>
          </dl>
        </section>

        <section className="fac-nuevo-tarjeta">
          <p className="fac-nuevo-rotulo">Receptor</p>
          <dl className="fac-nuevo-kv">
            <div className="fac-nuevo-kv__par">
              <dt>Razón social</dt>
              <dd>{comprobante.receptor_nombre}</dd>
            </div>
            <div className="fac-nuevo-kv__par">
              <dt>CUIT</dt>
              <dd className="fac-nuevo-fiscal">{comprobante.receptor_cuit}</dd>
            </div>
            <div className="fac-nuevo-kv__par">
              <dt>Condición de IVA</dt>
              <dd>{comprobante.receptor_condicion_iva.replaceAll("_", " ").toLowerCase()}</dd>
            </div>
            <div className="fac-nuevo-kv__par">
              <dt>Saldo pendiente</dt>
              <dd className="fac-nuevo-importe">
                {`$ ${formatearNumero(comprobante.saldo_pendiente)}`}
              </dd>
            </div>
          </dl>
        </section>
      </div>

      <section className="fac-nuevo-panel">
        <Tabla
          titulo="Detalle"
          columnas={COLUMNAS}
          filas={comprobante.items}
          claveDeFila={(fila) => fila.id}
          vacia="Este comprobante no tiene items."
        />
      </section>

      <div className="fac-nuevo-totales">
        <span>{`Subtotal: $ ${formatearNumero(comprobante.subtotal)}`}</span>
        <span>{`IVA: $ ${formatearNumero(comprobante.total_iva)}`}</span>
        <span className="fac-nuevo-totales__final">
          {`Total: $ ${formatearNumero(comprobante.total)}`}
        </span>
      </div>

      <div className="fac-nuevo-acciones">
        {comprobante.estado === "AUTORIZADO" && (
          <p className="fac-nuevo-inmutable">
            Un comprobante que ARCA autorizó no se modifica ni se borra: se reversa emitiendo una
            nota de crédito, que también va a ARCA y también queda.
          </p>
        )}
        {puedeAnular && (
          <Link
            href={`/facturacion/${comprobante.id}/anular`}
            className="boton boton--secundario fac-nuevo-boton-enlace"
          >
            Anular con nota de crédito
          </Link>
        )}
        {comprobante.descargable && (
          <Button
            onClick={() => {
              window.open(`/api/comprobantes/${comprobante.id}/pdf`, "_blank");
            }}
          >
            Descargar PDF
          </Button>
        )}
      </div>
    </>
  );
}
