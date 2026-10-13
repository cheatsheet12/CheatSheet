/**
 * La frontera del BFF para categorías y clasificación.
 *
 * Además de las dos propiedades de siempre —ninguna ruta llega al backend sin sesión, el
 * query string se reenvía entero— este archivo fija la que es propia de la unidad:
 * **existe un `DELETE`, y es el único de la aplicación**. Si algún día aparece otro,
 * conviene que sea una decisión y no una copia de acá.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

let cookieDeSesion: string | undefined;

vi.mock("next/headers", () => ({
  cookies: () => ({
    get: (nombre: string) =>
      nombre === "cheatsheet_session" && cookieDeSesion !== undefined
        ? { name: nombre, value: cookieDeSesion }
        : undefined,
    set: () => undefined,
    delete: () => undefined,
  }),
}));

const llamarApi = vi.fn();
vi.mock("@/lib/api", async () => {
  const real = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...real, llamarApi: (...args: unknown[]) => llamarApi(...args) };
});

const { ErrorDeApi } = await import("@/lib/api");
const { GET: getCategorias, POST: postCategoria } = await import("@/app/api/categorias/route");
const { PUT: putCategoria, DELETE: deleteCategoria } = await import(
  "@/app/api/categorias/[categoriaId]/route"
);
const { GET: getDeCliente, PUT: putDeCliente } = await import(
  "@/app/api/clientes/[clienteId]/categorias/route"
);
const { GET: getDeServicio, PUT: putDeServicio } = await import(
  "@/app/api/servicios/[servicioId]/categorias/route"
);

const CATEGORIA = {
  id: "3f1c2b8e-0000-4000-8000-000000000030",
  nombre: "VIP",
  aplica_a: "AMBOS",
};

function pedido(cuerpo: unknown = {}): Request {
  return new Request("http://test/api/categorias", {
    method: "POST",
    body: JSON.stringify(cuerpo),
  });
}

function lectura(url = "http://test/api/categorias"): Request {
  return new Request(url, { method: "GET" });
}

afterEach(() => {
  cookieDeSesion = undefined;
  llamarApi.mockReset();
});

describe("sin sesión", () => {
  it("ninguna ruta llega al backend, incluido el borrado", async () => {
    const respuestas = await Promise.all([
      getCategorias(lectura()),
      postCategoria(pedido({ nombre: "VIP", aplica_a: "CLIENTE" })),
      putCategoria(pedido({ nombre: "VIP" }), { params: { categoriaId: "una" } }),
      deleteCategoria(lectura(), { params: { categoriaId: "una" } }),
      getDeCliente(lectura(), { params: { clienteId: "un-cliente" } }),
      putDeCliente(pedido({ categoria_id: "una", asignar: true }), {
        params: { clienteId: "un-cliente" },
      }),
      getDeServicio(lectura(), { params: { servicioId: "un-servicio" } }),
      putDeServicio(pedido({ categoria_id: "una", asignar: true }), {
        params: { servicioId: "un-servicio" },
      }),
    ]);

    expect(respuestas.map((respuesta) => respuesta.status)).toEqual(Array(8).fill(401));
    expect(llamarApi).not.toHaveBeenCalled();
  });
});

describe("con sesión", () => {
  it("lista las categorías de la empresa", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ categorias: [CATEGORIA] });

    const respuesta = await getCategorias(lectura());

    expect(respuesta.status).toBe(200);
    expect(await respuesta.json()).toEqual({ categorias: [CATEGORIA] });
    expect(llamarApi).toHaveBeenCalledWith("/categorias", { method: "GET" });
  });

  it("reenvía el filtro de ámbito entero", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ categorias: [] });

    await getCategorias(lectura("http://test/api/categorias?aplica_a=CLIENTE"));

    expect(llamarApi).toHaveBeenCalledWith("/categorias?aplica_a=CLIENTE", { method: "GET" });
  });

  it("el borrado llega al backend como DELETE y sin cuerpo", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue(null);

    const respuesta = await deleteCategoria(lectura(), { params: { categoriaId: "c-1" } });

    expect(respuesta.status).toBe(200);
    expect(llamarApi).toHaveBeenCalledWith("/categorias/c-1", { method: "DELETE" });
  });

  it("clasificar manda el par completo y usa el id de la ruta", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ categorias: [CATEGORIA] });

    await putDeCliente(pedido({ categoria_id: CATEGORIA.id, asignar: true }), {
      params: { clienteId: "cl-1" },
    });
    await putDeServicio(pedido({ categoria_id: CATEGORIA.id, asignar: false }), {
      params: { servicioId: "sv-1" },
    });

    expect(llamarApi).toHaveBeenNthCalledWith(1, "/clientes/cl-1/categorias", {
      method: "PUT",
      body: { categoria_id: CATEGORIA.id, asignar: true },
    });
    expect(llamarApi).toHaveBeenNthCalledWith(2, "/servicios/sv-1/categorias", {
      method: "PUT",
      body: { categoria_id: CATEGORIA.id, asignar: false },
    });
  });

  it("leer las categorías de un elemento no manda cuerpo", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ categorias: [] });

    await getDeCliente(lectura(), { params: { clienteId: "cl-1" } });

    expect(llamarApi).toHaveBeenCalledWith("/clientes/cl-1/categorias", { method: "GET" });
  });

  it("el nombre duplicado llega con su mensaje, que es el texto de la historia", async () => {
    // `CategoriaDuplicada` es un `EntradaInvalida` —422— justamente por esto: el BFF
    // reenvía `detalle` sólo para ese código, y el mensaje de RN-02 está escrito para que
    // lo lea el usuario. Ver el docstring de la excepción.
    cookieDeSesion = "un-access-token";
    llamarApi.mockRejectedValue(
      new ErrorDeApi(
        422,
        "Ya existe una categoria con ese nombre en este ambito.",
        "EntradaInvalida",
      ),
    );

    const respuesta = await postCategoria(pedido({ nombre: "VIP", aplica_a: "CLIENTE" }));

    expect(respuesta.status).toBe(422);
    expect(await respuesta.json()).toEqual({
      error: "EntradaInvalida",
      detalle: "Ya existe una categoria con ese nombre en este ambito.",
    });
  });

  it("un 403 por rol llega con la frase del backend, como un 409", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockRejectedValue(
      new ErrorDeApi(403, "Se requiere rol Administrador u Operador", "PermisoDenegado"),
    );

    const respuesta = await deleteCategoria(lectura(), { params: { categoriaId: "c-1" } });

    expect(respuesta.status).toBe(403);
    expect(await respuesta.json()).toEqual({
      error: "PermisoDenegado",
      detalle: "Se requiere rol Administrador u Operador",
    });
  });
});
