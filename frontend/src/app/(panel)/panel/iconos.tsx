/**
 * Los iconos de PAN-DSH-01.
 *
 * Vienen de `lucide-react`, la misma librería que usa la barra lateral, así que un mismo
 * concepto se dibuja igual en todo el panel. Se importa glifo por glifo: el bundle lleva sólo
 * estos diez. La tabla `ICONOS` es la única que sabe qué glifo es cada nombre; el resto del
 * inicio habla de «documento» o «reloj» y no de un componente de la librería, de modo que
 * cambiar un dibujo es cambiar una línea acá.
 *
 * **Todos son `aria-hidden`.** Ninguno aporta información que el texto de al lado no diga: el
 * icono del calendario acompaña a la palabra «Turnos». Un `<svg>` anunciado además del texto
 * hace que el lector de pantalla lea la fila dos veces.
 */

import {
  Activity,
  CalendarDays,
  ChartColumn,
  Clock3,
  CloudUpload,
  CreditCard,
  ListChecks,
  type LucideIcon,
  Plus,
  ReceiptText,
  TriangleAlert,
} from "lucide-react";

export type NombreDeIcono =
  | "documento"
  | "tarjeta"
  | "calendario"
  | "reloj"
  | "actividad"
  | "barras"
  | "mas"
  | "subir"
  | "lista"
  | "alerta";

const ICONOS: Readonly<Record<NombreDeIcono, LucideIcon>> = {
  documento: ReceiptText,
  tarjeta: CreditCard,
  calendario: CalendarDays,
  reloj: Clock3,
  actividad: Activity,
  barras: ChartColumn,
  mas: Plus,
  subir: CloudUpload,
  lista: ListChecks,
  alerta: TriangleAlert,
};

export function Icono({ nombre }: { readonly nombre: NombreDeIcono }): JSX.Element {
  const Glifo = ICONOS[nombre];
  return <Glifo strokeWidth={1.9} aria-hidden="true" />;
}
