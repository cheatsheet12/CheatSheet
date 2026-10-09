/**
 * Las piezas que el listado (PAN-LOG-01) y el detalle (PAN-LOG-02) muestran igual.
 *
 * Están acá y no duplicadas en cada pantalla porque la marca del iniciador es la que hay que
 * poder reconocer de un vistazo: si el listado pinta al agente de IA de una manera y el
 * detalle de otra, deja de ser una marca y pasa a ser decoración.
 *
 * **El punto de color del módulo agrupa, no identifica.** Doce módulos no entran en doce
 * colores distinguibles; entran en cuatro familias — lo que factura, lo que cobra, lo que
 * conversa y lo que configura — que es la distinción que alguien hace escaneando la tabla.
 */

import {
  BookOpen,
  Bot,
  CalendarDays,
  ChartColumn,
  CreditCard,
  FileSpreadsheet,
  MessageCircle,
  Plug,
  ReceiptText,
  ScrollText,
  Settings2,
  ShieldCheck,
  User,
  Users,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { PREFERENCIAS_POR_DEFECTO } from "@/shared";

import { ETIQUETAS_DE_INICIADOR, ETIQUETAS_DE_MODULO } from "../api/bitacora";
import type { IniciadorDeOperacion } from "../api/bitacora";

/** Las cuatro familias del punto de color. Lo que no está acá se pinta neutro. */
const FAMILIA_DE_MODULO: Readonly<Record<string, string>> = {
  billing: "info",
  payments: "acento",
  spreadsheet_sync: "info",
  conversational: "alerta",
  scheduling: "alerta",
  reporting: "primario",
  observability: "primario",
  master_data: "acento",
};

/** Un icono por módulo: se reconoce más rápido que un punto de color y que una palabra. */
const ICONO_DE_MODULO: Readonly<Record<string, LucideIcon>> = {
  billing: ReceiptText,
  payments: CreditCard,
  spreadsheet_sync: FileSpreadsheet,
  conversational: MessageCircle,
  scheduling: CalendarDays,
  reporting: ChartColumn,
  observability: ScrollText,
  master_data: Users,
  identity: ShieldCheck,
  integrations: Plug,
  business_config: Settings2,
  reference_data: BookOpen,
};

const ICONO_DE_INICIADOR: Readonly<Record<IniciadorDeOperacion, LucideIcon>> = {
  usuario: User,
  sistema: Settings2,
  ia: Bot,
};

export interface PropsDeMarcaDeModulo {
  readonly modulo: string;
}

export function MarcaDeModulo({ modulo }: PropsDeMarcaDeModulo): JSX.Element {
  const familia = FAMILIA_DE_MODULO[modulo] ?? "neutro";
  const Icono = ICONO_DE_MODULO[modulo] ?? ScrollText;
  return (
    <span className="log-modulo">
      <span className={`log-modulo__icono log-modulo__icono--${familia}`} aria-hidden="true">
        <Icono size={15} strokeWidth={2} />
      </span>
      {ETIQUETAS_DE_MODULO[modulo] ?? modulo}
    </span>
  );
}

export interface PropsDeMarcaDeIniciador {
  readonly iniciador: IniciadorDeOperacion;
}

export function MarcaDeIniciador({ iniciador }: PropsDeMarcaDeIniciador): JSX.Element {
  const Icono = ICONO_DE_INICIADOR[iniciador];
  return (
    <span className={`log-por log-por--${iniciador}`}>
      <span className="log-por__tag" aria-hidden="true">
        <Icono size={14} strokeWidth={2.2} />
      </span>
      <span>{ETIQUETAS_DE_INICIADOR[iniciador]}</span>
    </span>
  );
}

/*
 * La fecha y la hora por separado, que es lo que la celda de dos líneas necesita.
 *
 * `formatearFechaHora` las devuelve pegadas en una sola cadena, y partir esa cadena por un
 * separador que depende del idioma es cómo se rompe el día que alguien cambia la
 * preferencia. Estos dos formateadores son de módulo y deterministas —zona horaria fija—,
 * así que el servidor y el navegador escriben exactamente lo mismo y no hay rehidratación
 * que difiera.
 */
const FECHA_LARGA = new Intl.DateTimeFormat(PREFERENCIAS_POR_DEFECTO.idioma, {
  day: "2-digit",
  month: "short",
  year: "numeric",
  timeZone: PREFERENCIAS_POR_DEFECTO.zonaHoraria,
});

const HORA_EXACTA = new Intl.DateTimeFormat(PREFERENCIAS_POR_DEFECTO.idioma, {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
  timeZone: PREFERENCIAS_POR_DEFECTO.zonaHoraria,
});

export function partirMomento(iso: string): { readonly fecha: string; readonly hora: string } {
  const fecha = new Date(iso);
  if (Number.isNaN(fecha.getTime())) {
    return { fecha: "—", hora: "" };
  }
  return { fecha: FECHA_LARGA.format(fecha), hora: HORA_EXACTA.format(fecha) };
}

export interface PropsDeMomento {
  readonly iso: string;
}

export function MomentoDeOperacion({ iso }: PropsDeMomento): JSX.Element {
  const { fecha, hora } = partirMomento(iso);
  return (
    <time className="log-ts" dateTime={iso}>
      <b>{fecha}</b>
      <span>{hora}</span>
    </time>
  );
}
