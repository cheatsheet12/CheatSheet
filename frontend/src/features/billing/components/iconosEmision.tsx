/**
 * Los iconos de «Nueva emisión».
 *
 * Vienen de `lucide-react`, como en el resto del panel, y se importan glifo por glifo. Todos son
 * `aria-hidden`: ninguno dice algo que el texto de al lado no diga. El tamaño lo da el CSS.
 */

import {
  ArrowLeft,
  Check,
  FilePlus2,
  FileText,
  ListPlus,
  Lock,
  Pencil,
  Plus,
  ReceiptText,
  ShieldCheck,
  Trash2,
  UserRound,
} from "lucide-react";

export function IconoDeTilde(): JSX.Element {
  return <Check aria-hidden="true" strokeWidth={3} />;
}

export function IconoDeCandado(): JSX.Element {
  return <Lock aria-hidden="true" strokeWidth={2} />;
}

export function IconoDeVolver(): JSX.Element {
  return <ArrowLeft aria-hidden="true" strokeWidth={2} />;
}

export function IconoDeEscudo(): JSX.Element {
  return <ShieldCheck aria-hidden="true" strokeWidth={2} />;
}

export function IconoDeLapiz(): JSX.Element {
  return <Pencil aria-hidden="true" strokeWidth={2} />;
}

export function IconoDeMas(): JSX.Element {
  return <Plus aria-hidden="true" strokeWidth={2.4} />;
}

export function IconoDeBasura(): JSX.Element {
  return <Trash2 aria-hidden="true" strokeWidth={2} />;
}

export function IconoDePersona(): JSX.Element {
  return <UserRound aria-hidden="true" strokeWidth={2} />;
}

export function IconoDeDocumento(): JSX.Element {
  return <FileText aria-hidden="true" strokeWidth={2} />;
}

export function IconoDeRecibo(): JSX.Element {
  return <ReceiptText aria-hidden="true" strokeWidth={2} />;
}

export function IconoDeItems(): JSX.Element {
  return <ListPlus aria-hidden="true" strokeWidth={2} />;
}

export function IconoDeNuevoDocumento(): JSX.Element {
  return <FilePlus2 aria-hidden="true" strokeWidth={2.2} />;
}
