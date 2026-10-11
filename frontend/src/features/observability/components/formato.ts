/**
 * Cómo se escribe, para una persona, lo que la bitácora guarda para una máquina.
 *
 * El backend registra `cliente_desactivado` y `ProcesamientoDePlanilla:0b5b129e-…`: son
 * identificadores estables, buenos para buscar y para auditar, y malos para leer. Estas
 * funciones sólo cambian la presentación; el texto original sigue en pantalla, en chico, para
 * quien necesite copiarlo o buscarlo, y nunca se manda ningún valor transformado a la API.
 */

/** `cliente_desactivado` → «Cliente desactivado». */
export function nombreDeAccion(accion: string): string {
  const texto = accion.replace(/_+/g, " ").trim();
  return texto === "" ? accion : texto.charAt(0).toUpperCase() + texto.slice(1);
}

/** `ProcesamientoDePlanilla` → «Procesamiento de planilla». */
function tipoLegible(tipo: string): string {
  const palabras = tipo
    .replace(/_+/g, " ")
    .replace(/([a-záéíóúñ])([A-ZÁÉÍÓÚÑ])/g, "$1 $2")
    .split(" ")
    .filter((palabra) => palabra !== "")
    .map((palabra) => palabra.toLowerCase());
  const [primera = "", ...resto] = palabras;
  return [primera.charAt(0).toUpperCase() + primera.slice(1), ...resto].join(" ");
}

export interface EntidadLegible {
  readonly tipo: string;
  /** Los primeros caracteres del identificador, para reconocerlo sin leer 36. */
  readonly corto: string;
  readonly completo: string;
}

/**
 * Parte `tipo:identificador` cuando el identificador es largo (un UUID). Si es corto —
 * `Comprobante:1` — no hay nada que acortar y se devuelve `null`: la pantalla muestra el
 * texto tal cual llegó.
 */
export function entidadLegible(entidad: string): EntidadLegible | null {
  const corte = entidad.indexOf(":");
  if (corte <= 0) {
    return null;
  }
  const id = entidad.slice(corte + 1);
  if (id.length <= 12) {
    return null;
  }
  return { tipo: tipoLegible(entidad.slice(0, corte)), corto: `${id.slice(0, 8)}…`, completo: id };
}
