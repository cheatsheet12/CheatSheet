/**
 * One card of PAN-CFG-INT.
 *
 * The layout is PAN-ONB-03's `int-card` from the Etapa 5 mockup
 * (`inputs/prototipos/pantallas/onboarding.html`), moved into configuration by decision
 * D7 of the units map. The logo square, the one-line description and the badge-plus-action
 * footer are taken as they are; the "PASO 3 DE 3" chrome is not.
 */

"use client";

import {
  CircleDashed,
  CreditCard,
  FileSpreadsheet,
  MessageCircle,
  ReceiptText,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { CSSProperties } from "react";

import { Button } from "@/shared";

import type { Ambiente, EstadoDeConexion, SistemaExterno } from "../api/cliente";

export interface DescripcionDeSistema {
  readonly nombre: string;
  readonly sigla: string;
  readonly color: string;
  readonly descripcion: string;
}

/** Copy and colours from the mockup. */
export const SISTEMAS: Readonly<Record<SistemaExterno, DescripcionDeSistema>> = {
  ARCA: {
    nombre: "ARCA",
    sigla: "AR",
    color: "#2A6FDB",
    descripcion: "Emití comprobantes fiscales electrónicos y consultá padrones automáticamente.",
  },
  MERCADOPAGO: {
    nombre: "MercadoPago",
    sigla: "MP",
    color: "#00B1EA",
    descripcion: "Generá links de pago y conciliá cobros sin esfuerzo.",
  },
  WHATSAPP: {
    nombre: "WhatsApp Business",
    sigla: "WA",
    color: "#00A879",
    descripcion:
      "Respondé clientes y mandá comprobantes con tu agente IA. La verificación de Meta demora 24–72 hs.",
  },
  GOOGLE_SHEETS: {
    nombre: "Google Sheets",
    sigla: "GS",
    color: "#1F8A5B",
    descripcion: "Sincronizá tus planillas de ventas, stock y clientes.",
  },
  EXCEL_ONLINE: {
    nombre: "Excel Online",
    sigla: "XL",
    color: "#1F6F43",
    descripcion: "Sincronizá tus planillas de ventas, stock y clientes.",
  },
};

//: Solo presentación: el ícono de cada sistema. El color de marca queda como un matiz
//: del recuadro, no como un relleno.
const ICONO: Readonly<Record<SistemaExterno, LucideIcon>> = {
  ARCA: ReceiptText,
  MERCADOPAGO: CreditCard,
  WHATSAPP: MessageCircle,
  GOOGLE_SHEETS: FileSpreadsheet,
  EXCEL_ONLINE: FileSpreadsheet,
};

const TEXTO: Readonly<Record<EstadoDeConexion, string>> = {
  CONECTADO: "Conectado",
  PENDIENTE: "Pendiente",
  ATENCION: "Atención",
  NO_CONECTADO: "Sin conectar",
};

const AMBIENTE: Readonly<Record<Ambiente, string>> = {
  HOMOLOGACION: "Homologación",
  PRODUCCION: "Producción",
};

export interface PropsDeTarjeta {
  readonly sistema: SistemaExterno;
  readonly estado: EstadoDeConexion;
  readonly detalle: string | null;
  readonly ambiente: Ambiente | null;
  /** The verified display name, once the provider reports one (HU-E2-03 RN-03). */
  readonly etiqueta: string | null;
  readonly configurada: boolean;
  /** Google Sheets has a card but no connector until epic 4. */
  readonly conectable: boolean;
  readonly puedeConectar: boolean;
  readonly ocupada: boolean;
  readonly onConectar: (sistema: SistemaExterno) => void;
}

export function TarjetaDeIntegracion({
  sistema,
  estado,
  detalle,
  ambiente,
  etiqueta,
  configurada,
  conectable,
  puedeConectar,
  ocupada,
  onConectar,
}: PropsDeTarjeta): JSX.Element {
  const info = SISTEMAS[sistema];
  // "indica la acción para reconectarla" — an integration that was connected and is now
  // down needs a different word from one that was never set up.
  const accion = configurada ? "Reconectar" : "Conectar";
  // Nothing to do while the provider is still deciding: the request is already in flight
  // on their side, and a "Reconectar" button here would invite the Administrator to start
  // a second review that resets the clock on the first.
  const enEspera = estado === "PENDIENTE";
  const partes = [etiqueta, ambiente !== null ? AMBIENTE[ambiente] : null].filter(
    (una): una is string => una !== null && una !== "",
  );
  const subtitulo = partes.length > 0 ? partes.join(" · ") : null;

  const Icono = ICONO[sistema];
  const alertado = estado === "ATENCION" || estado === "PENDIENTE";

  return (
    <article className="itg-card" data-estado={estado}>
      <div className="itg-card__top">
        <span
          className="itg-card__icono"
          style={{ "--itg-marca": info.color } as CSSProperties}
          aria-hidden="true"
        >
          <Icono size={22} strokeWidth={1.75} />
        </span>
        <div className="itg-card__titulo">
          <b>{info.nombre}</b>
          {/* The verified name identifies *which* account is connected, which matters more
              to the reader than the environment; the environment follows it.

              Both go in **one** span joined by the panel's separator. Two adjacent inline
              spans render with nothing between them — the card read
              «vence 2027-09-08Homologación», one word made of two facts. */}
          {subtitulo !== null ? <span className="itg-card__sub">{subtitulo}</span> : null}
        </div>
        <span className="itg-estado" data-estado={estado}>
          {TEXTO[estado]}
        </span>
      </div>
      <p className="itg-card__desc">{info.descripcion}</p>
      {detalle !== null ? (
        <p className={`itg-card__detalle${alertado ? " is-alerta" : ""}`}>{detalle}</p>
      ) : null}
      <div className="itg-card__foot">
        {conectable && puedeConectar && !enEspera ? (
          <Button
            variante="secundario"
            onClick={() => {
              onConectar(sistema);
            }}
            disabled={ocupada}
          >
            {accion}
          </Button>
        ) : null}
        {!conectable ? (
          <span className="itg-card__pronto">
            <CircleDashed size={14} aria-hidden="true" />
            <span>Disponible próximamente</span>
          </span>
        ) : null}
      </div>
    </article>
  );
}
