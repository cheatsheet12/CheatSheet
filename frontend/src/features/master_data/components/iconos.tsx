/**
 * Los iconos de las pantallas de Datos Maestros.
 *
 * Vienen de `lucide-react`, la misma librería que usa el resto del panel, así que un mismo
 * concepto se dibuja igual en todas las pantallas. Se importa glifo por glifo: el bundle lleva
 * sólo los de este archivo. Las pantallas hablan de «lupa» o «factura» y no de un componente de
 * la librería.
 *
 * **Todos son `aria-hidden`.** Ninguno dice algo que su texto de al lado —o el `aria-label` del
 * botón que lo contiene— no diga; anunciarlos haría que el lector de pantalla lea todo dos veces.
 * El tamaño lo da el CSS del contenedor, no el icono, y el color sale de `currentColor`.
 */

import {
  Banknote,
  CalendarPlus,
  Ellipsis,
  Mail,
  Pencil,
  Plus,
  Receipt,
  RotateCcw,
  Search,
  UserRound,
  UserX,
  Users,
  X,
} from "lucide-react";

const TRAZO = 2;

/** El «+» de los tres CTA: «Nuevo cliente», «Nuevo servicio» y «Nueva categoría». */
export function IconoDeMas(): JSX.Element {
  return <Plus aria-hidden="true" strokeWidth={2.4} />;
}

export function IconoDeLupa(): JSX.Element {
  return <Search aria-hidden="true" strokeWidth={TRAZO} />;
}

export function IconoDeLimpiar(): JSX.Element {
  return <X aria-hidden="true" strokeWidth={TRAZO} />;
}

export function IconoDeFactura(): JSX.Element {
  return <Receipt aria-hidden="true" strokeWidth={TRAZO} />;
}

export function IconoDeCobro(): JSX.Element {
  return <Banknote aria-hidden="true" strokeWidth={TRAZO} />;
}

export function IconoDeTurno(): JSX.Element {
  return <CalendarPlus aria-hidden="true" strokeWidth={TRAZO} />;
}

export function IconoDeEditar(): JSX.Element {
  return <Pencil aria-hidden="true" strokeWidth={TRAZO} />;
}

export function IconoDeMasAcciones(): JSX.Element {
  return <Ellipsis aria-hidden="true" strokeWidth={TRAZO} />;
}

export function IconoDeBaja(): JSX.Element {
  return <UserX aria-hidden="true" strokeWidth={TRAZO} />;
}

export function IconoDeReactivar(): JSX.Element {
  return <RotateCcw aria-hidden="true" strokeWidth={TRAZO} />;
}

export function IconoDeClientes(): JSX.Element {
  return <Users aria-hidden="true" strokeWidth={1.8} />;
}

export function IconoDeCliente(): JSX.Element {
  return <UserRound aria-hidden="true" strokeWidth={1.9} />;
}

export function IconoDeCorreo(): JSX.Element {
  return <Mail aria-hidden="true" strokeWidth={1.9} />;
}
