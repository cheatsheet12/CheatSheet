/**
 * Los iconos de las tres pantallas de ingesta.
 *
 * Vienen de `lucide-react`, la misma librería que usa el resto del panel, así que un mismo
 * concepto se dibuja igual en todas las pantallas. Se importa glifo por glifo: el bundle lleva
 * sólo los de esta tabla. La tabla `ICONOS` es la única que sabe qué glifo es cada nombre; las
 * pantallas hablan de «nube» o «planilla» y no de un componente de la librería.
 *
 * **Todos son `aria-hidden`.** Ninguno dice algo que su texto de al lado no diga; anunciarlos
 * haría que el lector de pantalla lea la fila dos veces.
 */

import {
  ArrowRight,
  Check,
  CloudUpload,
  Download,
  FileText,
  FileUp,
  Lock,
  ListChecks,
  type LucideIcon,
  RefreshCw,
  Sheet,
  Sparkles,
  TriangleAlert,
} from "lucide-react";

export type NombreDeIcono =
  | "nube"
  | "archivo"
  | "planilla"
  | "candado"
  | "chispa"
  | "refrescar"
  | "documento"
  | "alerta"
  | "tilde"
  | "flecha"
  | "descargar"
  | "lista";

const ICONOS: Readonly<Record<NombreDeIcono, LucideIcon>> = {
  nube: CloudUpload,
  archivo: FileUp,
  planilla: Sheet,
  candado: Lock,
  chispa: Sparkles,
  refrescar: RefreshCw,
  documento: FileText,
  alerta: TriangleAlert,
  tilde: Check,
  flecha: ArrowRight,
  descargar: Download,
  lista: ListChecks,
};

export function Icono({ nombre }: { readonly nombre: NombreDeIcono }): JSX.Element {
  const Glifo = ICONOS[nombre];
  return <Glifo strokeWidth={1.9} aria-hidden="true" />;
}
