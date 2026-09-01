/**
 * Lo que llaman PAN-DM-03 y el selector de clasificación.
 *
 * Dos propiedades bajo prueba, las mismas que en el cliente de API de `identity`: que cada
 * función pegue contra **el BFF de esta app** y nunca contra el backend —el navegador no
 * tiene token, y un `fetch` apuntado a la API desharía eso en silencio—, y que un fallo se
 * convierta en un error con el mensaje que el backend mandó.
 *
 * Y una tercera que es de esta unidad: **el borrado responde 204 sin cuerpo**. Es el único
 * `DELETE` de la aplicación, y un `.json()` sobre una respuesta vacía tira — así que hay
 * un test que lo fija.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

// Relativo y no por alias: `@/features/...` significa «alguien de afuera entrando», que es
// lo que prohíbe R5. El test de un módulo no es eso.
import {
  ErrorDeCategoria,
  categoriasDeCliente,
  categoriasDeServicio,
  clasificarCliente,
  clasificarServicio,
  crearCategoria,
  editarCategoria,
  eliminarCategoria,
  listarCategorias,
} from "../categoria";

const fetchFalso = vi.fn();
vi.stubGlobal("fetch", fetchFalso);

function responde(cuerpo: unknown, status = 200): void {
  fetchFalso.mockResolvedValue({
    ok: status < 400,
    status,
    json: async () => cuerpo,
  });
}

function respondeSinCuerpo(status = 204): void {
  fetchFalso.mockResolvedValue({
    ok: true,
    status,
    json: async () => {
      throw new SyntaxError("Unexpected end of JSON input");
    },
  });
}

function llamada(): { readonly ruta: string; readonly opciones: Record<string, unknown> } {
  const [ruta, opciones] = fetchFalso.mock.calls[0] as [string, Record<string, unknown>];
  return { ruta, opciones: opciones ?? {} };
}

const CATEGORIA = { id: "c-1", nombre: "VIP", aplica_a: "AMBOS" as const };

afterEach(() => {
  fetchFalso.mockReset();
});

describe("todas pegan contra el BFF", () => {
  it("ninguna ruta apunta al backend", async () => {
    responde({ categorias: [] });

    await listarCategorias();

    expect(llamada().ruta.startsWith("/api/")).toBe(true);
  });
});

describe("listar", () => {
  it("sin ambito no manda query string", async () => {
    responde({ categorias: [CATEGORIA] });

    const listado = await listarCategorias();

    expect(llamada().ruta).toBe("/api/categorias");
    expect(listado.categorias).toEqual([CATEGORIA]);
  });

  it("con ambito lo manda, y es lo que aplica RN-01 sin filtrar del lado del navegador", async () => {
    responde({ categorias: [] });

    await listarCategorias("CLIENTE");

    expect(llamada().ruta).toBe("/api/categorias?aplica_a=CLIENTE");
  });
});

describe("escrituras", () => {
  it("crear manda POST con el cuerpo del formulario", async () => {
    responde(CATEGORIA);

    await crearCategoria({ nombre: "VIP", aplica_a: "AMBOS" });

    const { ruta, opciones } = llamada();
    expect(ruta).toBe("/api/categorias");
    expect(opciones.method).toBe("POST");
    expect(JSON.parse(String(opciones.body))).toEqual({ nombre: "VIP", aplica_a: "AMBOS" });
  });

  it("editar manda PUT con el id en la ruta", async () => {
    responde(CATEGORIA);

    await editarCategoria("c-1", { nombre: "Premium", aplica_a: "CLIENTE" });

    const { ruta, opciones } = llamada();
    expect(ruta).toBe("/api/categorias/c-1");
    expect(opciones.method).toBe("PUT");
  });

  it("eliminar sobrevive a un 204 sin cuerpo", async () => {
    respondeSinCuerpo();

    await expect(eliminarCategoria("c-1")).resolves.toBeUndefined();

    const { ruta, opciones } = llamada();
    expect(ruta).toBe("/api/categorias/c-1");
    expect(opciones.method).toBe("DELETE");
    expect(opciones.body).toBeUndefined();
  });
});

describe("clasificacion", () => {
  it("leer las de un cliente devuelve el arreglo, no el sobre", async () => {
    responde({ categorias: [CATEGORIA] });

    const asignadas = await categoriasDeCliente("cl-1");

    expect(llamada().ruta).toBe("/api/clientes/cl-1/categorias");
    expect(asignadas).toEqual([CATEGORIA]);
  });

  it("leer las de un servicio, igual", async () => {
    responde({ categorias: [] });

    const asignadas = await categoriasDeServicio("sv-1");

    expect(llamada().ruta).toBe("/api/servicios/sv-1/categorias");
    expect(asignadas).toEqual([]);
  });

  it("asignar y quitar usan el mismo endpoint y difieren en `asignar`", async () => {
    responde({ categorias: [CATEGORIA] });
    await clasificarCliente("cl-1", "c-1", true);
    const asignando = llamada();

    fetchFalso.mockReset();
    responde({ categorias: [] });
    await clasificarCliente("cl-1", "c-1", false);
    const quitando = llamada();

    expect(asignando.ruta).toBe(quitando.ruta);
    expect(JSON.parse(String(asignando.opciones.body))).toEqual({
      categoria_id: "c-1",
      asignar: true,
    });
    expect(JSON.parse(String(quitando.opciones.body))).toEqual({
      categoria_id: "c-1",
      asignar: false,
    });
  });

  it("clasificar un servicio pega contra su propia ruta", async () => {
    responde({ categorias: [] });

    await clasificarServicio("sv-1", "c-1", true);

    expect(llamada().ruta).toBe("/api/servicios/sv-1/categorias");
  });
});

describe("fallos", () => {
  it("el mensaje del backend llega al que lo va a mostrar", async () => {
    responde({ detalle: "Ya existe una categoria con ese nombre en este ambito." }, 422);

    await expect(crearCategoria({ nombre: "VIP", aplica_a: "CLIENTE" })).rejects.toThrow(
      ErrorDeCategoria,
    );
    await expect(crearCategoria({ nombre: "VIP", aplica_a: "CLIENTE" })).rejects.toThrow(
      "Ya existe una categoria con ese nombre en este ambito.",
    );
  });

  it("un fallo sin `detalle` no deja a la pantalla sin nada que decir", async () => {
    responde({ error: "PermisoDenegado" }, 403);

    await expect(listarCategorias()).rejects.toThrow("No se pudo completar la operacion");
  });
});
