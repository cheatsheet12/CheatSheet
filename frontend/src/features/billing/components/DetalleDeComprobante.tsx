/**
 * PAN-FAC-02 — Facturación · Detalle (HU-E5-02).
 *
 * Todo lo que pide RN-02 —número, tipo, fecha, receptor, ítems, total, CAE y su
 * vencimiento— y nada que pueda cambiarlo. **Acá no hay ninguna edición**, y eso es RN-01 y
 * no un olvido: un comprobante autorizado es inmutable, y un formulario que dejara
 * intentarlo sería un formulario cuyo botón Guardar sólo puede fallar. La frase al lado de
 * las acciones lo dice por escrito: la única salida es una nota de crédito.
 *
 * **El número, el CAE y el CUIT van en monoespaciada** y con botón de copiar: son
 * identificadores fiscales que alguien compara carácter por carácter contra un papel o dicta
 * por teléfono.
 *
 * **La descarga se ofrece sólo para un comprobante autorizado** y en su lugar se muestra el
 * motivo del rechazo cuando lo hay, con las palabras de ARCA, sin parafrasear.
 *
 * **Los importes son texto de la API**: se les da formato para mostrarlos y no se opera con
 * ellos.
 */

"use client";

import { Download, FileMinus2, Landmark, Lock, UserRound } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { Alert, Badge, Tabla, formatearFecha, formatearFechaHora, formatearNumero } from "@/shared";
import type { Columna } from "@/shared";

import { ETIQUETAS_DE_ESTADO, numeroFormateado, tonoDeEstado } from "../api/comprobante";
import type { Anulacion, Comprobante, ItemDeComprobante } from "../api/comprobante";
import { ETIQUETAS_DE_TIPO } from "../api/puntoDeVenta";
import { AvatarDeReceptor } from "./AvatarDeReceptor";
import { BotonDeCopiar } from "./BotonDeCopiar";

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

function Avisos({
  comprobante,
  anulacion,
}: {
  readonly comprobante: Comprobante;
  readonly anulacion: Anulacion | null;
}): JSX.Element {
  return (
    // Los avisos juntos y arriba de todo: son lo que cambia qué significa el resto de la
    // pantalla, así que se leen antes que el comprobante y no intercalados en él.
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
          {anulacion.es_total ? "." : `, con $ ${formatearNumero(anulacion.disponible)} vigentes.`}
        </Alert>
      )}

      {comprobante.motivo_de_rechazo !== null && (
        // ARCA's own words: not translated, so a numeric code never ends up meaning
        // something else in a message somebody takes to their accountant.
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
  );
}

function Dato({
  titulo,
  children,
}: {
  readonly titulo: string;
  readonly children: ReactNode;
}): JSX.Element {
  return (
    <div className="fac-det-dato">
      <dt>{titulo}</dt>
      <dd>{children}</dd>
    </div>
  );
}

export function DetalleDeComprobante({
  comprobante,
  puntoNumero,
  anulacion = null,
  puedeAnular = false,
}: PropsDeDetalleDeComprobante): JSX.Element {
  return (
    <>
      <Avisos comprobante={comprobante} anulacion={anulacion} />

      {/* El número una sola vez y en grande: es el dato con el que alguien reconoce este
          comprobante, y repetirlo abajo sólo daría dos lugares donde mirar. */}
      <header className="fac-det-cabecera">
        <div className="fac-det-cabecera__principal">
          <div className="fac-det-identidad">
            <span className="fac-det-tipo">{ETIQUETAS_DE_TIPO[comprobante.tipo]}</span>
            <h1 className="fac-det-numero">{numeroFormateado(comprobante, puntoNumero)}</h1>
            <p className="fac-det-meta">
              <Badge estado={tonoDeEstado(comprobante.estado)}>
                {ETIQUETAS_DE_ESTADO[comprobante.estado]}
              </Badge>
              <span>Emitido el {formatearFechaHora(comprobante.fecha_emision)}</span>
            </p>
          </div>
          <div className="fac-det-total">
            <span className="fac-det-total__rotulo">Total</span>
            <strong className="fac-det-total__valor">{`$ ${formatearNumero(comprobante.total)}`}</strong>
          </div>
        </div>

        <div className="fac-det-acciones">
          {comprobante.descargable && (
            <button
              type="button"
              className="fac-cta fac-cta--compacto"
              onClick={() => {
                window.open(`/api/comprobantes/${comprobante.id}/pdf`, "_blank");
              }}
            >
              <Download aria-hidden="true" />
              Descargar PDF
            </button>
          )}
          {puedeAnular && (
            <Link href={`/facturacion/${comprobante.id}/anular`} className="fac-det-secundario">
              <FileMinus2 aria-hidden="true" size={16} />
              Anular con nota de crédito
            </Link>
          )}
          {comprobante.estado === "AUTORIZADO" && (
            <p className="fac-det-nota">
              <Lock aria-hidden="true" size={14} />
              Un comprobante que ARCA autorizó no se modifica ni se borra: se reversa emitiendo una
              nota de crédito, que también va a ARCA y también queda.
            </p>
          )}
        </div>
      </header>

      <div className="fac-det-columnas">
        <section className="fac-det-tarjeta" aria-labelledby="fac-det-fiscales">
          <h2 className="fac-det-tarjeta__titulo" id="fac-det-fiscales">
            <span className="fac-det-azulejo" aria-hidden="true">
              <Landmark size={17} />
            </span>
            Datos fiscales
          </h2>
          <dl className="fac-det-datos">
            <Dato titulo="CAE">
              <span className="fac-det-mono">{comprobante.cae ?? "—"}</span>
              {comprobante.cae !== null && (
                <BotonDeCopiar valor={comprobante.cae} etiqueta="Copiar CAE" />
              )}
            </Dato>
            <Dato titulo="Vencimiento del CAE">
              <span className="fac-det-mono">{formatearFecha(comprobante.cae_vence_el)}</span>
            </Dato>
            <Dato titulo="Punto de venta">
              <span className="fac-det-mono">
                {puntoNumero === null ? "—" : String(puntoNumero).padStart(4, "0")}
              </span>
            </Dato>
          </dl>
        </section>

        <section className="fac-det-tarjeta" aria-labelledby="fac-det-receptor">
          <h2 className="fac-det-tarjeta__titulo" id="fac-det-receptor">
            <span className="fac-det-azulejo" aria-hidden="true">
              <UserRound size={17} />
            </span>
            Receptor
          </h2>
          <div className="fac-det-persona">
            <AvatarDeReceptor nombre={comprobante.receptor_nombre} grande />
            <div className="fac-det-persona__datos">
              <span className="fac-det-persona__nombre">{comprobante.receptor_nombre}</span>
              <span className="fac-det-persona__sub">
                {comprobante.receptor_condicion_iva.replaceAll("_", " ").toLowerCase()}
              </span>
            </div>
          </div>
          <dl className="fac-det-datos">
            <Dato titulo="CUIT">
              <span className="fac-det-mono">{comprobante.receptor_cuit}</span>
              <BotonDeCopiar valor={comprobante.receptor_cuit} etiqueta="Copiar CUIT" />
            </Dato>
            <Dato titulo="Saldo pendiente">
              <span className="fac-nuevo-importe">
                {`$ ${formatearNumero(comprobante.saldo_pendiente)}`}
              </span>
            </Dato>
          </dl>
        </section>
      </div>

      <section className="fac-nuevo-panel fac-det-items">
        <h2 className="fac-det-items__titulo">Ítems del comprobante</h2>
        <Tabla
          titulo="Detalle"
          columnas={COLUMNAS}
          filas={comprobante.items}
          claveDeFila={(fila) => fila.id}
          vacia="Este comprobante no tiene items."
        />
      </section>

      <dl className="fac-det-resumen">
        <div className="fac-det-resumen__fila">
          <dt>Subtotal</dt>
          <dd>{`$ ${formatearNumero(comprobante.subtotal)}`}</dd>
        </div>
        <div className="fac-det-resumen__fila">
          <dt>IVA</dt>
          <dd>{`$ ${formatearNumero(comprobante.total_iva)}`}</dd>
        </div>
        <div className="fac-det-resumen__fila fac-det-resumen__fila--final">
          <dt>Total</dt>
          <dd>{`$ ${formatearNumero(comprobante.total)}`}</dd>
        </div>
      </dl>
    </>
  );
}
