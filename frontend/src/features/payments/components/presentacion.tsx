/**
 * Lo que las pantallas de cobros **dibujan** a partir de un cobro: iniciales, variante de
 * avatar, referencia corta y el resto de días hasta el vencimiento.
 *
 * Vive fuera de los componentes por una razón concreta: son funciones puras con reglas de
 * borde —un concepto de una sola palabra, un vencimiento que cae hoy, un id más corto de lo
 * esperado— y probarlas a través de un `render` obliga a montar media pantalla para afirmar
 * sobre una cadena de dos letras.
 *
 * **Nada de esto es dominio.** Ninguna de estas funciones decide qué se le cobra a nadie:
 * deciden qué letra va adentro de un cuadradito de 34 píxeles.
 */

import type { ReactNode } from "react";

import type { EstadoCobro } from "../api/cobro";

/** Las cuatro variantes de avatar que define `pantallas-cobros.css`. */
export const VARIANTES_DE_AVATAR = 4;

/**
 * Dos letras a partir de un texto.
 *
 * Toma la inicial de las dos primeras palabras con contenido; si hay una sola, sus dos
 * primeras letras. Un texto vacío devuelve «—» y no una cadena vacía: un avatar en blanco se
 * lee como algo que no cargó.
 */
export function inicialesDe(texto: string): string {
  const palabras = texto
    .split(/\s+/)
    .map((palabra) => palabra.replace(/[^\p{L}\p{N}]/gu, ""))
    .filter((palabra) => palabra !== "");

  if (palabras.length === 0) {
    return "—";
  }
  if (palabras.length === 1) {
    return (palabras[0] ?? "").slice(0, 2).toUpperCase();
  }
  return `${(palabras[0] ?? "").slice(0, 1)}${(palabras[1] ?? "").slice(0, 1)}`.toUpperCase();
}

/**
 * Qué variante de color le toca a un identificador, entre 1 y `VARIANTES_DE_AVATAR`.
 *
 * Determinista a propósito: el mismo cobro tiene que verse igual en el listado y en el
 * detalle, y un color al azar por render haría parpadear la fila en cada filtrado.
 */
export function varianteDeAvatar(id: string): number {
  let acumulado = 0;
  for (const caracter of id) {
    acumulado = (acumulado + (caracter.codePointAt(0) ?? 0)) % 9973;
  }
  return (acumulado % VARIANTES_DE_AVATAR) + 1;
}

/**
 * La referencia corta que se ve debajo del concepto, al estilo `CB-4F2A9C11`.
 *
 * El id completo es un UUID que nadie dicta por teléfono. Los ocho primeros caracteres
 * alcanzan para reconocer una fila y para buscarla, y es lo que muestra el prototipo.
 */
export function referenciaDeCobro(id: string): string {
  const limpio = id.replace(/-/g, "").toUpperCase();
  return `CB-${limpio.slice(0, 8)}`;
}

export interface RestoHastaVencimiento {
  readonly texto: string;
  /** Qué tan urgente es, para elegir el color sin volver a comparar fechas en el JSX. */
  readonly tono: "ok" | "pronto" | "tarde";
}

/**
 * Cuánto falta para el vencimiento, en palabras.
 *
 * Recibe el día de hoy como argumento en vez de leer el reloj: una función que llama a
 * `new Date()` adentro es una función que no se puede probar sin congelar el tiempo, y una
 * pantalla que la llama durante el render del servidor y otra vez al hidratar puede obtener
 * dos días distintos si el render cae sobre la medianoche.
 */
export function restoHastaVencimiento(venceEl: string, hoy: string): RestoHastaVencimiento | null {
  const dias = diasEntre(hoy, venceEl);
  if (dias === null) {
    return null;
  }
  if (dias === 0) {
    return { texto: "vence hoy", tono: "pronto" };
  }
  if (dias < 0) {
    const atraso = Math.abs(dias);
    return { texto: `hace ${atraso} ${atraso === 1 ? "día" : "días"}`, tono: "tarde" };
  }
  return {
    texto: `en ${dias} ${dias === 1 ? "día" : "días"}`,
    tono: dias <= 2 ? "pronto" : "ok",
  };
}

function diasEntre(desde: string, hasta: string): number | null {
  const inicio = Date.parse(`${desde.slice(0, 10)}T00:00:00Z`);
  const fin = Date.parse(`${hasta.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(inicio) || Number.isNaN(fin)) {
    return null;
  }
  return Math.round((fin - inicio) / 86_400_000);
}

/**
 * Qué tono de badge le toca al estado de entrega de un recordatorio.
 *
 * `null` es «todavía no salió», que no es lo mismo que «salió y no sabemos qué pasó»: el
 * primero es una promesa y el segundo es un problema.
 */
export function tonoDeEntrega(estado: string | null): "ok" | "atencion" | "pendiente" | "error" {
  if (estado === null) {
    return "pendiente";
  }
  const normalizado = estado.toUpperCase();
  if (normalizado === "ENVIADO" || normalizado === "LEIDO" || normalizado === "ENTREGADO") {
    return "ok";
  }
  if (normalizado === "FALLIDO" || normalizado === "RECHAZADO" || normalizado === "ERROR") {
    return "error";
  }
  return "atencion";
}

/** Qué color de fondo lleva la caja del monto, según el estado del cobro. */
export function tonoDeCaja(estado: EstadoCobro): "ok" | "atencion" | "error" | "neutral" {
  if (estado === "APROBADO") {
    return "ok";
  }
  if (estado === "VENCIDO") {
    return "error";
  }
  if (estado === "PENDIENTE") {
    return "atencion";
  }
  return "neutral";
}

/*
 * Los íconos son SVG inline y no una fuente ni un paquete: son cuatro trazos, y una
 * dependencia nueva para dibujarlos costaría más kilobytes que las pantallas enteras.
 * Todos van con `aria-hidden`, porque al lado de cada uno hay texto que dice lo mismo.
 */

function svg(hijos: ReactNode, grosor = 2): JSX.Element {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={grosor} aria-hidden>
      {hijos}
    </svg>
  );
}

export const ICONO_TILDE = svg(
  <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />,
  2.2,
);

export const ICONO_RELOJ = svg(
  <>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" strokeLinecap="round" />
  </>,
);

export const ICONO_ALERTA = svg(
  <path
    d="M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"
    strokeLinecap="round"
    strokeLinejoin="round"
  />,
);

export const ICONO_BARRAS = svg(
  <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" strokeLinecap="round" />,
);

export const ICONO_CHAT = svg(
  <path d="M12 3a9 9 0 0 0-7.8 13.5L3 21l4.7-1.2A9 9 0 1 0 12 3Z" strokeLinecap="round" />,
  1.8,
);
