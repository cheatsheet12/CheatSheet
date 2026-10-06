/**
 * What PAN-DM-02 calls.
 *
 * **`precio` is a `string` on both sides of every call, and that is the point.** A
 * JavaScript `number` is an IEEE-754 double — the same float the backend refuses to accept
 * — so the moment a price becomes one, the binary error is in the system and nothing
 * downstream can tell. Keeping it text means the panel can display it and never
 * accidentally arithmetic on it.
 *
 * The panel does not compute the price with VAT either. It shows the net price and the
 * rate, which is what the acceptance criterion asks for; multiplying is `billing`'s, in
 * epic 5, and doing it here would be business logic in the frontend (`CLAUDE.md` §5).
 */

import type { OrigenDato } from "./cliente";

/** The three rates of HU-E4-02 RN-02. The value **is** the rate, as the backend sends it. */
export type AlicuotaIVA = "0.00" | "0.105" | "0.21";

export interface Servicio {
  readonly id: string;
  readonly nombre: string;
  /** Text, always. See the module docstring. */
  readonly precio: string;
  readonly alicuota_iva: AlicuotaIVA;
  readonly agendable: boolean;
  readonly duracion_estandar_min: number | null;
  readonly origen: OrigenDato;
  readonly activo: boolean;
}

export interface ListadoDeServicios {
  readonly servicios: readonly Servicio[];
  readonly total: number;
}

export interface DatosDeServicio {
  readonly nombre: string;
  readonly precio: string;
  readonly alicuota_iva: AlicuotaIVA;
  readonly agendable: boolean;
  /** Whole minutes. The form refuses non-integer text; the 5-to-480 range is the backend's. */
  readonly duracion_estandar_min?: number | null;
}

/** How each rate is written for a person. The backend never sends a label. */
export const ETIQUETAS_DE_ALICUOTA: Readonly<Record<AlicuotaIVA, string>> = {
  "0.00": "0%",
  "0.105": "10,5%",
  "0.21": "21%",
};

export class ErrorDeServicio extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = "ErrorDeServicio";
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
    const detalle = (datos as { detalle?: string }).detalle;
    throw new ErrorDeServicio(detalle ?? "No se pudo completar la operacion");
  }
  return datos as T;
}

export interface FiltrosDeServicios {
  readonly texto?: string;
  readonly agendable?: boolean | null;
  readonly soloActivos?: boolean;
  /** HU-E4-04, del lado de los servicios. */
  readonly categoriaId?: string;
}

function consulta(filtros: FiltrosDeServicios): string {
  const parametros = new URLSearchParams();
  if (filtros.texto !== undefined && filtros.texto.trim() !== "") {
    parametros.set("texto", filtros.texto.trim());
  }
  if (filtros.agendable !== undefined && filtros.agendable !== null) {
    parametros.set("agendable", String(filtros.agendable));
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

export async function listarServicios(
  filtros: FiltrosDeServicios = {},
): Promise<ListadoDeServicios> {
  return pedir<ListadoDeServicios>(`/api/servicios${consulta(filtros)}`, "GET");
}

export async function crearServicio(datos: DatosDeServicio): Promise<Servicio> {
  return pedir<Servicio>("/api/servicios", "POST", datos);
}

export async function editarServicio(id: string, datos: DatosDeServicio): Promise<Servicio> {
  return pedir<Servicio>(`/api/servicios/${id}`, "PUT", datos);
}

/** Deactivate or reactivate. **There is no delete**, on this side either. */
export async function cambiarEstadoDeServicio(id: string, activo: boolean): Promise<Servicio> {
  return pedir<Servicio>(`/api/servicios/${id}/estado`, "PUT", { activo });
}
