/**
 * Del error del backend a una frase que una persona entiende.
 *
 * El backend contesta `{ error: "<Codigo>", detalle?: "<frase>" }`. Cuando hay `detalle` es una
 * frase escrita para quien la lee (la de la historia o la de ARCA) y se muestra tal cual. Cuando
 * sólo hay un código técnico —`ErrorInterno`, `EntradaInvalida` sin detalle— mostrarlo crudo no
 * le dice nada a nadie: acá se traduce, en un único lugar, sin tocar el contrato con la API.
 */

import { ErrorDeComprobante } from "./comprobante";

export type AccionDeFacturacion = "validar" | "emitir";

const POR_DEFECTO: Readonly<Record<AccionDeFacturacion, string>> = {
  validar: "No pudimos validar el CUIT ahora. Probá de nuevo en un momento.",
  emitir:
    "No pudimos emitir el comprobante ahora. Antes de reintentar, revisá el listado por si se emitió.",
};

const POR_CODIGO: Readonly<Record<string, Readonly<Record<AccionDeFacturacion, string>>>> = {
  EntradaInvalida: {
    validar: "Revisá el CUIT: tiene que tener 11 dígitos y ser un número válido.",
    emitir: "Revisá los datos del comprobante: hay algo que ARCA no puede aceptar.",
  },
  ArcaNoDisponible: {
    validar: "ARCA no responde en este momento. Probá de nuevo en unos minutos.",
    emitir:
      "ARCA no responde en este momento. Antes de reintentar, revisá el listado por si se emitió.",
  },
  NoAutenticado: {
    validar: "Tu sesión venció. Volvé a iniciar sesión para continuar.",
    emitir: "Tu sesión venció. Volvé a iniciar sesión para continuar.",
  },
  Prohibido: {
    validar: "Tu usuario no tiene permiso para validar receptores.",
    emitir: "Tu usuario no tiene permiso para emitir comprobantes.",
  },
};

/** `ErrorInterno`, `ArcaNoDisponible`: una sola palabra en CamelCase, sin espacios ni puntos. */
function pareceUnCodigo(texto: string): boolean {
  return /^[A-Z][A-Za-z0-9]+$/.test(texto);
}

export function mensajeLegible(fallo: unknown, accion: AccionDeFacturacion): string {
  if (!(fallo instanceof ErrorDeComprobante)) {
    // Un fallo de red u otro que no vino del backend: no hay frase que mostrar.
    return POR_DEFECTO[accion];
  }
  if (fallo.detalle !== null && fallo.detalle.trim() !== "") {
    return fallo.detalle;
  }
  const codigo = fallo.codigo ?? (pareceUnCodigo(fallo.message) ? fallo.message : null);
  if (codigo === null) {
    return fallo.message;
  }
  return POR_CODIGO[codigo]?.[accion] ?? POR_DEFECTO[accion];
}
