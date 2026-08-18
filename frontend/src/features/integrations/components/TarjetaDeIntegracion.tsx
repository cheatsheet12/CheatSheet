/**
 * One card of PAN-CFG-INT.
 *
 * The layout is PAN-ONB-03's `int-card` from the Etapa 5 mockup
 * (`inputs/prototipos/pantallas/onboarding.html`), moved into configuration by decision
 * D7 of the units map. The logo square, the one-line description and the badge-plus-action
 * footer are taken as they are; the "PASO 3 DE 3" chrome is not.
 */

"use client";

import { Badge, Button } from "@/shared";
import type { EstadoDeBadge } from "@/shared";

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

const TONO: Readonly<Record<EstadoDeConexion, EstadoDeBadge>> = {
  CONECTADO: "ok",
  ATENCION: "atencion",
  NO_CONECTADO: "error",
};

const TEXTO: Readonly<Record<EstadoDeConexion, string>> = {
  CONECTADO: "Conectado",
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

  return (
    <article className={`int-card${estado === "CONECTADO" ? " is-on" : ""}`}>
      <div className="int-card__top">
        <span className="int-logo" style={{ background: info.color }} aria-hidden="true">
          {info.sigla}
        </span>
        <div>
          <b>{info.nombre}</b>
          {ambiente !== null ? <span className="int-card__sub">{AMBIENTE[ambiente]}</span> : null}
        </div>
      </div>
      <p>{info.descripcion}</p>
      {detalle !== null ? <p className="int-card__detalle">{detalle}</p> : null}
      <div className="int-card__foot">
        <Badge estado={TONO[estado]}>{TEXTO[estado]}</Badge>
        {conectable && puedeConectar ? (
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
        {!conectable ? <span className="int-card__pronto">Disponible próximamente</span> : null}
      </div>
    </article>
  );
}
