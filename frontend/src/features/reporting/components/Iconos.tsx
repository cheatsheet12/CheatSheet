/**
 * Los pictogramas de las tres pantallas de reportería.
 *
 * Vienen de `lucide-react`, la misma librería que usan la barra lateral y el inicio, así que un
 * mismo concepto se dibuja igual en todo el panel. Se importa glifo por glifo: el bundle lleva
 * sólo estos catorce. Cada función conserva su nombre para que las pantallas no cambien; lo
 * único que sabe qué dibujo es cada una es este archivo.
 *
 * Son decorativos: el texto que acompaña a cada uno ya dice lo que el icono ilustra, y un
 * lector de pantalla que los anunciara leería dos veces lo mismo. De ahí el `aria-hidden`.
 */

import {
  Check,
  ChartColumn,
  CalendarDays,
  Clock3,
  CircleHelp,
  CreditCard,
  Download,
  Eye,
  ListChecks,
  type LucideIcon,
  ReceiptText,
  Send,
  TriangleAlert,
  UserRound,
  X,
} from "lucide-react";

function pictograma(Glifo: LucideIcon): () => JSX.Element {
  return function Pictograma(): JSX.Element {
    return <Glifo strokeWidth={1.9} aria-hidden="true" focusable="false" />;
  };
}

export const IconoDocumento = pictograma(ReceiptText);
export const IconoTarjeta = pictograma(CreditCard);
export const IconoCalendario = pictograma(CalendarDays);
export const IconoReloj = pictograma(Clock3);
export const IconoLista = pictograma(ListChecks);
export const IconoAlerta = pictograma(TriangleAlert);
export const IconoBarras = pictograma(ChartColumn);
export const IconoDescarga = pictograma(Download);
export const IconoTilde = pictograma(Check);
export const IconoCruz = pictograma(X);
export const IconoEnvio = pictograma(Send);
export const IconoPersona = pictograma(UserRound);
export const IconoPregunta = pictograma(CircleHelp);
export const IconoOjo = pictograma(Eye);
