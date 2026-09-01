/**
 * What PAN-DM-01 calls.
 *
 * These talk to **this app's** route handlers, never to the backend directly: the BFF is
 * what holds the session cookie, and a browser cannot attach an HttpOnly cookie it is not
 * allowed to read (ADR-011).
 *
 * **`ErrorDeCatalogo` carries the duplicate's id**, and that is the only reason this file
 * has an error class of its own. HU-E4-01 asks the screen to «ofrecer ver el duplicado»,
 * so the 409 has to arrive as something more than a message.
 */

export type OrigenDato = "PLANILLA" | "PANEL" | "AGENTE";

export type CondicionIVA = "RESPONSABLE_INSCRIPTO" | "MONOTRIBUTO" | "EXENTO" | "CONSUMIDOR_FINAL";

/** The three answers the registry can give. Never two — see the backend's padrón module. */
export type EstadoDeConsulta = "ENCONTRADO" | "NO_ENCONTRADO" | "NO_DISPONIBLE";

export interface DatosDePadron {
  readonly razon_social: string | null;
  readonly condicion_iva: CondicionIVA | null;
  readonly activo: boolean;
}

export interface ResultadoDePadron {
  readonly estado: EstadoDeConsulta;
  readonly datos: DatosDePadron | null;
  readonly motivo: string | null;
}

export interface Cliente {
  readonly id: string;
  readonly nombre: string;
  /** Already formatted by the API as `30-71234567-1`. */
  readonly cuit: string | null;
  readonly condicion_iva: CondicionIVA | null;
  readonly contacto_whatsapp: string | null;
  readonly contacto_email: string | null;
  readonly origen: OrigenDato;
  readonly activo: boolean;
  /**
   * How ARCA answered on this save. Absent on reads and when there was no CUIT to ask
   * about; `NO_DISPONIBLE` is what the form turns into «no se pudo validar».
   */
  readonly validacion?: ResultadoDePadron | null;
}

export interface ListadoDeClientes {
  readonly clientes: readonly Cliente[];
  readonly total: number;
}

/** What the form sends. Every field optional: only the backend decides what is required. */
export interface DatosDeCliente {
  readonly nombre?: string;
  readonly cuit?: string;
  readonly condicion_iva?: CondicionIVA | null;
  readonly contacto_whatsapp?: string;
  readonly contacto_email?: string;
}

export class ErrorDeCatalogo extends Error {
  constructor(
    mensaje: string,
    /** Present only on a duplicate CUIT: the client that already holds it. */
    readonly clienteExistenteId: string | null = null,
  ) {
    super(mensaje);
    this.name = "ErrorDeCatalogo";
  }
}

async function pedir<T>(
  ruta: string,
  metodo: "GET" | "POST" | "PUT",
  cuerpo?: unknown,
): Promise<T> {
  const respuesta = await fetch(ruta, {
    method: metodo,
    ...(cuerpo !== undefined
      ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo) }
      : {}),
  });
  const datos: unknown = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    const cuerpoDeError = datos as { detalle?: string; cliente_existente_id?: string };
    throw new ErrorDeCatalogo(
      cuerpoDeError.detalle ?? "No se pudo completar la operacion",
      cuerpoDeError.cliente_existente_id ?? null,
    );
  }
  return datos as T;
}

export interface FiltrosDeListado {
  readonly texto?: string;
  readonly origen?: OrigenDato | "";
  readonly soloActivos?: boolean;
  /** HU-E4-04: «es filtrable por esa categoria». */
  readonly categoriaId?: string;
}

function consulta(filtros: FiltrosDeListado): string {
  const parametros = new URLSearchParams();
  if (filtros.texto !== undefined && filtros.texto.trim() !== "") {
    parametros.set("texto", filtros.texto.trim());
  }
  if (filtros.origen !== undefined && filtros.origen !== "") {
    parametros.set("origen", filtros.origen);
  }
  if (filtros.soloActivos === true) {
    parametros.set("solo_activos", "true");
  }
  if (filtros.categoriaId !== undefined && filtros.categoriaId !== "") {
    parametros.set("categoria_id", filtros.categoriaId);
  }
  const cadena = parametros.toString();
  return cadena === "" ? "" : `?${cadena}`;
}

export async function listarClientes(filtros: FiltrosDeListado = {}): Promise<ListadoDeClientes> {
  return pedir<ListadoDeClientes>(`/api/clientes${consulta(filtros)}`, "GET");
}

export async function crearCliente(datos: DatosDeCliente): Promise<Cliente> {
  return pedir<Cliente>("/api/clientes", "POST", datos);
}

export async function editarCliente(id: string, datos: DatosDeCliente): Promise<Cliente> {
  return pedir<Cliente>(`/api/clientes/${id}`, "PUT", datos);
}

/**
 * Deactivate or reactivate. **There is no delete**, on this side either: the API grants
 * none, so offering one here would be a button that can only fail.
 */
export async function cambiarEstadoDeCliente(id: string, activo: boolean): Promise<Cliente> {
  return pedir<Cliente>(`/api/clientes/${id}/estado`, "PUT", { activo });
}

/**
 * The «Validar contra ARCA» button.
 *
 * A `POST` on a read, like the onboarding's: the CUIT is somebody's tax id and in a query
 * string it would end up in access logs and in browser history.
 */
export async function consultarPadron(cuit: string): Promise<ResultadoDePadron> {
  return pedir<ResultadoDePadron>("/api/clientes/padron", "POST", { cuit });
}
