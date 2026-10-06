/**
 * What PAN-ING-01 calls.
 *
 * **The size and the extension are checked here too**, before a byte leaves the browser.
 * Not because the backend cannot be trusted to — it refuses the same two things and that
 * is the guarantee — but because uploading 30 MB in order to be told it was too big is a
 * minute of somebody's tethered connection spent on a foregone answer. The messages are
 * the ones HU-E3-03 writes, so the user reads the same sentence whichever side refused.
 */

/** Mirrors `ProveedorPlanilla` in the backend. `ARCHIVO` is decision D10 of the map. */
export type ProveedorPlanilla = "GOOGLE_SHEETS" | "EXCEL_ONLINE" | "ARCHIVO";
export type DireccionSync = "SOLO_LECTURA" | "LECTURA_Y_ESCRITURA";

export interface Vinculo {
  readonly id: string;
  readonly proveedor: ProveedorPlanilla;
  readonly direccion: DireccionSync;
  readonly hoja_empresa: string;
  /** Con lo que la persona identificó la planilla al vincularla. */
  readonly identificador_externo?: string | null;
  readonly nombre_archivo: string | null;
  readonly tamano_bytes: number | null;
  readonly pausado: boolean;
  readonly motivo_de_pausa: string | null;
  readonly escribe_de_vuelta: boolean;
  readonly tiene_mapeo: boolean;
  readonly ultima_lectura: string | null;
  readonly created_at: string;
}

export interface ListadoDeVinculos {
  readonly vinculos: readonly Vinculo[];
}

/** HU-E3-03, word for word. Shared with the backend's `domain/valores.py`. */
export const EXTENSIONES_ACEPTADAS = [".xlsx", ".xls", ".csv"] as const;
export const LIMITE_TAMANO_MB = 25;
export const LIMITE_TAMANO_BYTES = LIMITE_TAMANO_MB * 1024 * 1024;
export const MENSAJE_FORMATO_NO_ACEPTADO = "Formato no aceptado. Use .xlsx, .xls o .csv.";
export const MENSAJE_ARCHIVO_DEMASIADO_GRANDE = `El archivo supera el límite de ${LIMITE_TAMANO_MB} MB.`;

/** How each provider is named on screen. The backend never sends a label. */
export const ETIQUETAS_DE_PROVEEDOR: Readonly<Record<ProveedorPlanilla, string>> = {
  GOOGLE_SHEETS: "Google Sheets",
  EXCEL_ONLINE: "Excel Online",
  ARCHIVO: "Archivo subido",
};

export class ErrorDePlanilla extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = "ErrorDePlanilla";
  }
}

interface CuerpoDeError {
  readonly error?: string;
  readonly detalle?: string;
}

async function fallar(respuesta: Response): Promise<never> {
  const cuerpo = (await respuesta.json().catch(() => ({}))) as CuerpoDeError;
  // `detalle` first: on a 422 the backend's sentence is the one the story wrote, and it
  // is more specific than anything this file could invent.
  throw new ErrorDePlanilla(cuerpo.detalle ?? cuerpo.error ?? "No se pudo completar la operacion");
}

export async function listarPlanillas(): Promise<ListadoDeVinculos> {
  const respuesta = await fetch("/api/planillas", { cache: "no-store" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as ListadoDeVinculos;
}

/** The two checks of HU-E3-03, run before the upload starts. See the module docstring. */
export function validarArchivo(archivo: File): void {
  const nombre = archivo.name.toLowerCase();
  if (!EXTENSIONES_ACEPTADAS.some((ext) => nombre.endsWith(ext))) {
    throw new ErrorDePlanilla(MENSAJE_FORMATO_NO_ACEPTADO);
  }
  if (archivo.size > LIMITE_TAMANO_BYTES) {
    throw new ErrorDePlanilla(MENSAJE_ARCHIVO_DEMASIADO_GRANDE);
  }
}

export async function subirPlanilla(archivo: File): Promise<Vinculo> {
  validarArchivo(archivo);

  const respuesta = await fetch(
    `/api/planillas/archivo?nombre=${encodeURIComponent(archivo.name)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: archivo,
    },
  );
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Vinculo;
}

/**
 * El identificador de una planilla de Google, sacado de su enlace.
 *
 * Una URL de Google Sheets es `.../spreadsheets/d/<id>/edit#gid=0`. Se acepta también el
 * id pelado, porque alguien que ya lo conoce no tiene por qué ir a buscar el enlace.
 */
export function identificadorDePlanilla(enlace: string): string | null {
  const limpio = enlace.trim();
  if (limpio === "") {
    return null;
  }
  const enLaUrl = /\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/.exec(limpio);
  if (enLaUrl !== null) {
    return enLaUrl[1] ?? null;
  }
  // Cualquier otra cosa se toma como el nombre con el que la persona la va a reconocer.
  // Contra el proveedor real un nombre no resuelve a ningún documento y el backend lo
  // dirá; contra el simulado alcanza, y es lo que permite recorrer el flujo sin tener una
  // planilla de Google a mano.
  return limpio;
}

export async function iniciarVinculacionConGoogle(documento: string): Promise<string> {
  const respuesta = await fetch("/api/planillas/google/autorizacion", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ documento }),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  const { url } = (await respuesta.json()) as { readonly url: string };
  return url;
}

export async function desvincularPlanilla(vinculoId: string): Promise<void> {
  const respuesta = await fetch(`/api/planillas/${vinculoId}`, { method: "DELETE" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
}

// --- PAN-ING-02 — revisión del mapeo (HU-E3-01, HU-E3-02) --------------------

/** Los tres niveles de HU-E3-01 RN-01, en las palabras que usa la pantalla. */
export type NivelDeConfianza = "ALTA" | "MEDIA" | "BAJA";

export interface EntradaDeMapeo {
  readonly columna_origen: string;
  /** `null` es el «Sin asignar» de RN-03, y es una respuesta válida. */
  readonly atributo_destino: string | null;
  readonly confianza: NivelDeConfianza;
  /** Leído de la planilla y mostrado acá. Nunca pasó por el modelo (decisión D12). */
  readonly ejemplo: string | null;
  readonly corregida_a_mano: boolean;
}

export interface Mapeo {
  readonly id: string;
  readonly estado: string;
  readonly version: number;
  readonly entradas: readonly EntradaDeMapeo[];
  /** Atributos obligatorios que ninguna columna alimenta todavía (RN-02). */
  readonly faltantes: readonly string[];
  readonly puede_confirmarse: boolean;
  readonly propuesto_por_el_modelo: boolean;
  /** RN-02: se reusó el mapeo guardado para esta estructura y no se llamó al modelo. */
  readonly reutilizado?: boolean;
}

/** Cómo se llama cada campo interno en pantalla. El backend nunca manda etiquetas. */
export const ETIQUETAS_DE_ATRIBUTO: Readonly<Record<string, string>> = {
  nombre: "Nombre / Razón social",
  cuit: "CUIT",
  condicion_iva: "Condición de IVA",
  contacto_whatsapp: "WhatsApp",
  contacto_email: "Email",
  precio: "Precio",
  alicuota_iva: "Alícuota de IVA",
  agendable: "Agendable",
  duracion_estandar_min: "Duración (min)",
};

export const ATRIBUTOS_DE_CLIENTE = [
  "nombre",
  "cuit",
  "condicion_iva",
  "contacto_whatsapp",
  "contacto_email",
] as const;

export const MENSAJE_FALTAN_OBLIGATORIAS =
  "Debe asignar todas las columnas obligatorias antes de continuar.";

export async function proponerMapeo(
  vinculoId: string,
  columnas: readonly { nombre: string; ejemplo?: string }[],
): Promise<Mapeo> {
  const respuesta = await fetch("/api/planillas/mapeos", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ vinculo_id: vinculoId, columnas }),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Mapeo;
}

export async function corregirMapeo(
  mapeoId: string,
  columna: string,
  atributo: string | null,
): Promise<Mapeo> {
  const respuesta = await fetch(`/api/planillas/mapeos/${mapeoId}/columnas`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ columna, atributo }),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Mapeo;
}

export async function confirmarMapeo(mapeoId: string): Promise<Mapeo> {
  const respuesta = await fetch(`/api/planillas/mapeos/${mapeoId}/confirmacion`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Mapeo;
}

// --- PAN-ING-03 — resultado de un procesamiento (HU-E3-03, HU-E3-05, HU-E3-06) ----

/** Los cuatro estados. `CON_ERRORES` es el que la historia llama «Con errores». */
export type EstadoProcesamiento = "EN_CURSO" | "COMPLETADO" | "CON_ERRORES" | "FALLIDO";

export interface Carga {
  readonly id: string;
  readonly estado: EstadoProcesamiento;
  readonly filas_totales: number;
  readonly filas_ok: number;
  readonly filas_error: number;
  readonly es_reproceso: boolean;
  readonly created_at: string;
}

export interface ErrorDeFila {
  /** El número de fila del archivo original (HU-E3-05 RN-02). */
  readonly numero_fila: number;
  readonly motivo: string;
  /** Una persona la corrigió en el sistema. El error se conserva como historia. */
  readonly corregida: boolean;
}

/** Un campo del sistema y el valor que la fila tiene en el archivo (puede estar vacío). */
export interface CampoDeFila {
  readonly atributo: string;
  readonly valor: string;
}

/** Lo que el editor de una fila fallida necesita: por qué falló y qué contiene. */
export interface FilaConError {
  readonly numero_fila: number;
  readonly motivo: string;
  readonly campos: readonly CampoDeFila[];
}

export interface DetalleDeCarga {
  readonly carga: Carga;
  readonly errores: readonly ErrorDeFila[];
  /** False para Solo Lectura (RN-04) y también cuando no falló nada. */
  readonly puede_reprocesar: boolean;
}

export interface ListadoDeCargas {
  readonly cargas: readonly Carga[];
}

/** Cómo se llama cada estado en pantalla, con las palabras de HU-E3-03. */
export const ETIQUETAS_DE_ESTADO: Readonly<Record<EstadoProcesamiento, string>> = {
  EN_CURSO: "Procesando",
  COMPLETADO: "Procesado",
  CON_ERRORES: "Con errores",
  FALLIDO: "Fallido",
};

export async function listarCargas(vinculoId?: string): Promise<ListadoDeCargas> {
  const consulta = vinculoId === undefined ? "" : `?vinculo_id=${encodeURIComponent(vinculoId)}`;
  const respuesta = await fetch(`/api/planillas/cargas${consulta}`, { cache: "no-store" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as ListadoDeCargas;
}

export async function verCarga(cargaId: string): Promise<DetalleDeCarga> {
  const respuesta = await fetch(`/api/planillas/cargas/${cargaId}`, { cache: "no-store" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as DetalleDeCarga;
}

/**
 * Devuelve un mapeo confirmado al estado de revisión, conservando lo ya asignado.
 *
 * Es la salida que el propio mensaje del dominio nombra —«para cambiarlo hay que revisarlo
 * de nuevo»— y que hasta ahora sólo usaba la sincronización automática.
 */
export async function reabrirMapeo(mapeoId: string): Promise<Mapeo> {
  const respuesta = await fetch(`/api/planillas/mapeos/${mapeoId}/revision`, { method: "POST" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as Mapeo;
}

export async function procesarPlanilla(vinculoId: string): Promise<void> {
  const respuesta = await fetch("/api/planillas/cargas", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ vinculo_id: vinculoId }),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
}

/** Los valores de una fila que falló, leídos del archivo y mapeados a campos del sistema. */
export async function verFilaConError(cargaId: string, numeroFila: number): Promise<FilaConError> {
  const respuesta = await fetch(`/api/planillas/cargas/${cargaId}/filas/${numeroFila}`, {
    cache: "no-store",
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as FilaConError;
}

/**
 * Importa la fila con los valores corregidos y devuelve el detalle actualizado de la carga.
 *
 * Si el sistema la rechaza (un CUIT que sigue mal) levanta `ErrorDePlanilla` con el motivo,
 * y no se cambió nada: el editor sigue abierto para corregirla de nuevo.
 */
export async function corregirFila(
  cargaId: string,
  numeroFila: number,
  valores: Readonly<Record<string, string>>,
): Promise<DetalleDeCarga> {
  const respuesta = await fetch(`/api/planillas/cargas/${cargaId}/filas/${numeroFila}/correccion`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ valores }),
  });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as DetalleDeCarga;
}

export async function reprocesarCarga(cargaId: string): Promise<void> {
  const respuesta = await fetch(`/api/planillas/cargas/${cargaId}/reproceso`, { method: "POST" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
}

/**
 * El listado de errores que HU-E3-05 RN-03 deja descargar «para su corrección externa».
 *
 * Se arma en el navegador y no se pide al backend: los datos ya están en pantalla, y un
 * endpoint de descarga sería una segunda copia de las mismas filas viajando por la red
 * para producir un archivo que el navegador puede escribir solo.
 */
export function csvDeErrores(errores: readonly ErrorDeFila[]): string {
  const escapar = (valor: string): string => `"${valor.replace(/"/g, '""')}"`;
  const filas = errores.map((e) => `${e.numero_fila},${escapar(e.motivo)}`);
  return ["fila,motivo", ...filas].join("\n");
}
