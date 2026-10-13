/**
 * Cómo se escribe, para una persona, lo que la bitácora guarda para una máquina.
 *
 * El backend registra `cliente_desactivado` y `ProcesamientoDePlanilla:0b5b129e-…`: son
 * identificadores estables, buenos para buscar y para auditar, y malos para leer. Estas
 * funciones sólo cambian la presentación; el texto original sigue en pantalla, en chico, para
 * quien necesite copiarlo o buscarlo, y nunca se manda ningún valor transformado a la API.
 */

/**
 * Las palabras que los identificadores escriben sin tilde (#175). Es la lista de las que usan
 * las acciones que registra el backend; una que falte se lee sin tilde, como antes, y no rompe.
 */
const CON_TILDE: Readonly<Record<string, string>> = {
  aceptacion: "aceptación",
  alicuota: "alícuota",
  anticipacion: "anticipación",
  anulacion: "anulación",
  atencion: "atención",
  auditoria: "auditoría",
  autorizacion: "autorización",
  bitacora: "bitácora",
  cancelacion: "cancelación",
  catalogos: "catálogos",
  categoria: "categoría",
  comparacion: "comparación",
  conciliacion: "conciliación",
  condicion: "condición",
  configuracion: "configuración",
  correccion: "corrección",
  credito: "crédito",
  derivacion: "derivación",
  descripcion: "descripción",
  dia: "día",
  dias: "días",
  duracion: "duración",
  envio: "envío",
  estandar: "estándar",
  excepcion: "excepción",
  facturacion: "facturación",
  habilitacion: "habilitación",
  integracion: "integración",
  invalida: "inválida",
  invitacion: "invitación",
  leida: "leída",
  lineas: "líneas",
  operacion: "operación",
  padron: "padrón",
  parametros: "parámetros",
  politica: "política",
  proxima: "próxima",
  proximo: "próximo",
  renovacion: "renovación",
  reprogramacion: "reprogramación",
  revocacion: "revocación",
  sesion: "sesión",
  sincronizacion: "sincronización",
  terminos: "términos",
  verificacion: "verificación",
};

/** Frases que el identificador dice en inglés, y cómo se dicen en el panel. */
const EN_ESPANOL: readonly (readonly [RegExp, string])[] = [
  // El estado se llama «No se presentó» en todo el panel.
  [/\bno show\b/g, "como no presentado"],
];

/** `cliente_desactivado` → «Cliente desactivado»; `registrar_excepcion` → «Registrar excepción». */
export function nombreDeAccion(accion: string): string {
  let texto = accion.replace(/_+/g, " ").trim();
  if (texto === "") {
    return accion;
  }
  for (const [frase, traduccion] of EN_ESPANOL) {
    texto = texto.replace(frase, traduccion);
  }
  texto = texto
    .split(" ")
    .map((palabra) => CON_TILDE[palabra] ?? palabra)
    .join(" ");
  return texto.charAt(0).toUpperCase() + texto.slice(1);
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
