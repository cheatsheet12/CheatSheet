/**
 * What PAN-DM-03 and the two classification controls call.
 *
 * **`listarCategorias(ambito)` filters by usability, not equality.** Asking for `CLIENTE`
 * also returns the `AMBOS` ones, because those are assignable to a client — and that rule
 * lives in the backend, so the dropdown here does not have to know it. This is HU-E4-04
 * RN-01's acceptance criterion («el sistema no ofrece esa categoría») satisfied by asking
 * the right question rather than by filtering afterwards.
 */

export type AmbitoDeCategoria = "CLIENTE" | "SERVICIO" | "AMBOS";

export interface Categoria {
  readonly id: string;
  readonly nombre: string;
  readonly aplica_a: AmbitoDeCategoria;
}

export interface ListadoDeCategorias {
  readonly categorias: readonly Categoria[];
}

export interface DatosDeCategoria {
  readonly nombre: string;
  readonly aplica_a: AmbitoDeCategoria;
}

/** How each scope is written for a person. */
export const ETIQUETAS_DE_AMBITO: Readonly<Record<AmbitoDeCategoria, string>> = {
  CLIENTE: "Clientes",
  SERVICIO: "Servicios",
  AMBOS: "Clientes y servicios",
};

export class ErrorDeCategoria extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = "ErrorDeCategoria";
  }
}

async function pedir<T>(
  ruta: string,
  metodo: "GET" | "POST" | "PUT" | "DELETE",
  cuerpo?: unknown,
): Promise<T> {
  const respuesta = await fetch(ruta, {
    method: metodo,
    ...(cuerpo !== undefined
      ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo) }
      : {}),
  });
  if (respuesta.status === 204) {
    return undefined as T;
  }
  const datos: unknown = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    const detalle = (datos as { detalle?: string }).detalle;
    throw new ErrorDeCategoria(detalle ?? "No se pudo completar la operacion");
  }
  return datos as T;
}

export async function listarCategorias(aplica_a?: AmbitoDeCategoria): Promise<ListadoDeCategorias> {
  const consulta = aplica_a !== undefined ? `?aplica_a=${aplica_a}` : "";
  return pedir<ListadoDeCategorias>(`/api/categorias${consulta}`, "GET");
}

export async function crearCategoria(datos: DatosDeCategoria): Promise<Categoria> {
  return pedir<Categoria>("/api/categorias", "POST", datos);
}

export async function editarCategoria(id: string, datos: DatosDeCategoria): Promise<Categoria> {
  return pedir<Categoria>(`/api/categorias/${id}`, "PUT", datos);
}

/**
 * The one delete in the whole panel.
 *
 * HU-E4-03 RN-03: the classified elements lose the label and keep everything else. The
 * confirmation is the caller's — `Button variante="destructivo"` already asks.
 */
export async function eliminarCategoria(id: string): Promise<void> {
  await pedir<void>(`/api/categorias/${id}`, "DELETE");
}

/** What the element already carries, so the checkboxes open already ticked. */
export async function categoriasDeCliente(clienteId: string): Promise<readonly Categoria[]> {
  const listado = await pedir<ListadoDeCategorias>(`/api/clientes/${clienteId}/categorias`, "GET");
  return listado.categorias;
}

export async function categoriasDeServicio(servicioId: string): Promise<readonly Categoria[]> {
  const listado = await pedir<ListadoDeCategorias>(
    `/api/servicios/${servicioId}/categorias`,
    "GET",
  );
  return listado.categorias;
}

/** Assigns when `asignar` is true, removes when false. Returns the element's new set. */
export async function clasificarCliente(
  clienteId: string,
  categoriaId: string,
  asignar: boolean,
): Promise<ListadoDeCategorias> {
  return pedir<ListadoDeCategorias>(`/api/clientes/${clienteId}/categorias`, "PUT", {
    categoria_id: categoriaId,
    asignar,
  });
}

export async function clasificarServicio(
  servicioId: string,
  categoriaId: string,
  asignar: boolean,
): Promise<ListadoDeCategorias> {
  return pedir<ListadoDeCategorias>(`/api/servicios/${servicioId}/categorias`, "PUT", {
    categoria_id: categoriaId,
    asignar,
  });
}
