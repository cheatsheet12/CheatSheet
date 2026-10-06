/**
 * What PAN-LOG-01 and PAN-LOG-02 call (HU-E12-01, HU-E12-02).
 *
 * **Los filtros viajan con el mismo texto que el listado devuelve** — `identity`, `ia`,
 * `error` — y no con el nombre del miembro del enum. Un filtro que hay que escribir distinto
 * de como se lee obliga a traducir de este lado, y esa traducción es donde una mayúscula de
 * más devuelve la lista entera.
 *
 * **No hay `eliminar` ni `editar`.** HU-E12-01 RN-04: la bitácora es de sólo consulta. El
 * backend no otorga el permiso, así que una función acá sólo podría fallar.
 */

export type ResultadoDeOperacion = "completado" | "error";
export type IniciadorDeOperacion = "usuario" | "sistema" | "ia";

export interface Operacion {
  readonly id: string;
  readonly timestamp: string;
  readonly modulo: string;
  readonly accion: string;
  readonly entidad_afectada: string;
  readonly iniciador: IniciadorDeOperacion;
  readonly resultado: ResultadoDeOperacion;
  readonly usuario_id: string | null;
}

export interface ListadoDeOperaciones {
  readonly operaciones: readonly Operacion[];
  readonly total: number;
}

export interface DetalleDeOperacion {
  readonly operacion: Operacion;
  /** Lo que la operación registró de sí misma. Vacío en casi todas. */
  readonly detalle: Readonly<Record<string, string>>;
  readonly timeline: readonly Operacion[];
  /** `null` cuando dejó una sola fila: no hay duración medida. */
  readonly duracion_ms: number | null;
  readonly paso_con_error: string | null;
}

export interface FiltrosDeBitacora {
  readonly desde?: string;
  readonly hasta?: string;
  readonly modulo?: string;
  readonly resultado?: string;
  readonly iniciador?: string;
  readonly texto?: string;
  readonly pagina?: number;
}

/** HU-E12-01, palabra por palabra, para el estado vacío de PAN-LOG-01. */
export const MENSAJE_SIN_OPERACIONES = "No hay operaciones para los filtros seleccionados.";

/** Cuántas filas trae una página. El mismo número que el backend pagina. */
export const TAMANO_DE_PAGINA = 25;

/** Los doce módulos, con el nombre que se lee en pantalla. */
export const ETIQUETAS_DE_MODULO: Readonly<Record<string, string>> = {
  identity: "Identidad",
  master_data: "Datos maestros",
  business_config: "Configuración",
  integrations: "Integraciones",
  spreadsheet_sync: "Sincronización",
  billing: "Facturación",
  payments: "Cobros",
  scheduling: "Agenda",
  conversational: "Conversaciones",
  observability: "Auditoría",
  reporting: "Reportes",
  reference_data: "Datos de referencia",
};

/**
 * Cómo se lee cada iniciador (HU-E12-01 RN-02).
 *
 * «Agente IA» y no «IA» a secas: lo que la fila dice es que actuó el agente de WhatsApp sobre
 * el mensaje de un cliente, y esa es la distinción por la que alguien filtra.
 */
export const ETIQUETAS_DE_INICIADOR: Readonly<Record<IniciadorDeOperacion, string>> = {
  usuario: "Usuario",
  sistema: "Sistema",
  ia: "Agente IA",
};

export const ETIQUETAS_DE_RESULTADO: Readonly<Record<ResultadoDeOperacion, string>> = {
  completado: "Completado",
  error: "Error",
};

export class ErrorDeBitacora extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = "ErrorDeBitacora";
  }
}

interface CuerpoDeError {
  readonly error?: string;
  readonly detalle?: string;
}

async function fallar(respuesta: Response): Promise<never> {
  const cuerpo = (await respuesta.json().catch(() => ({}))) as CuerpoDeError;
  // `detalle` primero: en un 422 la frase del backend es la que explica por qué —incluido
  // «el rol Solo Lectura no accede a la bitácora», que no es un error sino una regla.
  throw new ErrorDeBitacora(cuerpo.detalle ?? cuerpo.error ?? "No se pudo completar la operacion");
}

function consultaDe(filtros: FiltrosDeBitacora): string {
  const parametros = new URLSearchParams();
  for (const [clave, valor] of Object.entries(filtros)) {
    if (valor !== undefined && valor !== "" && valor !== 1) {
      parametros.set(clave, String(valor));
    }
  }
  const texto = parametros.toString();
  return texto === "" ? "" : `?${texto}`;
}

export async function listarOperaciones(
  filtros: FiltrosDeBitacora = {},
): Promise<ListadoDeOperaciones> {
  const respuesta = await fetch(`/api/bitacora${consultaDe(filtros)}`, { cache: "no-store" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as ListadoDeOperaciones;
}

export async function verOperacion(operacionId: string): Promise<DetalleDeOperacion> {
  const respuesta = await fetch(`/api/bitacora/${operacionId}`, { cache: "no-store" });
  if (!respuesta.ok) {
    await fallar(respuesta);
  }
  return (await respuesta.json()) as DetalleDeOperacion;
}
