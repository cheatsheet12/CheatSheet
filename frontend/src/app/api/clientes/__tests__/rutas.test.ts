/**
 * La frontera del BFF para el catálogo de clientes.
 *
 * La misma propiedad que las otras rutas del panel: **ninguna llega al backend sin
 * sesión**, y el token de la cookie HttpOnly nunca sale hacia el navegador.
 *
 * Y una que es propia de estas: el listado **reenvía el query string tal cual**. Es
 * deliberado y conviene que un test lo fije — si el handler reconstruyera los filtros uno
 * por uno, el día que llegue el filtro por categoría de `categorias-y-clasificacion` habría
 * que editar dos lugares, y el que se olvide silencia un filtro en vez de romper.
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
const { GET: getClientes, POST: postCliente } = await import("@/app/api/clientes/route");
const { GET: getCliente, PUT: putCliente } = await import("@/app/api/clientes/[clienteId]/route");
const { PUT: putEstado } = await import("@/app/api/clientes/[clienteId]/estado/route");
const { POST: postPadron } = await import("@/app/api/clientes/padron/route");

const CLIENTE = {
  id: "3f1c2b8e-0000-4000-8000-000000000010",
  nombre: "Panaderia Dona Rosa",
  cuit: "30-71234567-1",
  condicion_iva: "RESPONSABLE_INSCRIPTO",
  contacto_whatsapp: "5491112345678",
  contacto_email: "rosa@panaderia.com",
  origen: "PANEL",
  activo: true,
};

function pedido(cuerpo: unknown = {}, url = "http://test/api/clientes"): Request {
  return new Request(url, { method: "POST", body: JSON.stringify(cuerpo) });
}

function listado(consulta = ""): Request {
  return new Request(`http://test/api/clientes${consulta}`, { method: "GET" });
}

afterEach(() => {
  cookieDeSesion = undefined;
  llamarApi.mockReset();
});

describe("sin sesión", () => {
  it("ninguna ruta llega al backend", async () => {
    const respuestas = await Promise.all([
      getClientes(listado()),
      getCliente(listado(), { params: { clienteId: "un-cliente" } }),
      postCliente(pedido({ nombre: "Rosa" })),
      putCliente(pedido({ nombre: "Rosa" }), { params: { clienteId: "un-cliente" } }),
      putEstado(pedido({ activo: false }), { params: { clienteId: "un-cliente" } }),
      postPadron(pedido({ cuit: "30712345671" })),
    ]);

    expect(respuestas.map((respuesta) => respuesta.status)).toEqual(Array(6).fill(401));
    expect(llamarApi).not.toHaveBeenCalled();
  });
});

describe("con sesión", () => {
  it("lista el catálogo de la empresa", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ clientes: [CLIENTE], total: 1 });

    const respuesta = await getClientes(listado());

    expect(respuesta.status).toBe(200);
    expect(await respuesta.json()).toEqual({ clientes: [CLIENTE], total: 1 });
    expect(llamarApi).toHaveBeenCalledWith("/clientes", { method: "GET" });
  });

  it("trae un cliente por el id de la ruta", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue(CLIENTE);

    const respuesta = await getCliente(listado(), { params: { clienteId: "c-1" } });

    expect(respuesta.status).toBe(200);
    expect(await respuesta.json()).toEqual(CLIENTE);
    expect(llamarApi).toHaveBeenCalledWith("/clientes/c-1", { method: "GET" });
  });

  it("reenvía el query string entero, sin conocer los filtros", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ clientes: [], total: 0 });

    await getClientes(listado("?texto=rosa&origen=PANEL&solo_activos=true"));

    expect(llamarApi).toHaveBeenCalledWith("/clientes?texto=rosa&origen=PANEL&solo_activos=true", {
      method: "GET",
    });
  });

  it("el alta manda el cuerpo del formulario tal como llegó", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue(CLIENTE);

    const respuesta = await postCliente(pedido({ nombre: "Rosa", cuit: "30712345671" }));

    expect(respuesta.status).toBe(200);
    expect(llamarApi).toHaveBeenCalledWith("/clientes", {
      method: "POST",
      body: { nombre: "Rosa", cuit: "30712345671" },
    });
  });

  it("la edición y el cambio de estado usan el id de la ruta", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue(CLIENTE);

    await putCliente(pedido({ nombre: "Rosa Diaz" }), { params: { clienteId: "c-1" } });
    await putEstado(pedido({ activo: false }), { params: { clienteId: "c-1" } });

    expect(llamarApi).toHaveBeenNthCalledWith(1, "/clientes/c-1", {
      method: "PUT",
      body: { nombre: "Rosa Diaz" },
    });
    expect(llamarApi).toHaveBeenNthCalledWith(2, "/clientes/c-1/estado", {
      method: "PUT",
      body: { activo: false },
    });
  });

  it("el CUIT viaja en el cuerpo y no en la URL", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ estado: "NO_DISPONIBLE", datos: null, motivo: "sin ARCA" });

    await postPadron(pedido({ cuit: "30712345671" }, "http://test/api/clientes/padron"));

    const [ruta, opciones] = llamarApi.mock.calls[0] as [string, { body: unknown }];
    expect(ruta).toBe("/clientes/padron");
    expect(ruta).not.toContain("30712345671");
    expect(opciones.body).toEqual({ cuit: "30712345671" });
  });

  it("un 409 del backend llega como 409, con su código y con su mensaje", async () => {
    // `TODO.md` §10: el mensaje de `ClienteDuplicado` se perdía en el BFF, así que la
    // pantalla mostraba «No se pudo completar la operacion» en vez del texto de la
    // historia. El proxy ahora reenvía el detalle de un 409 — la sesión ya está
    // verificada y no hay nada que enumerar, a diferencia de las rutas de `auth`.
    cookieDeSesion = "un-access-token";
    llamarApi.mockRejectedValue(
      new ErrorDeApi(409, "Ya existe un cliente con ese CUIT.", "ClienteDuplicado"),
    );

    const respuesta = await postCliente(pedido({ nombre: "Rosa", cuit: "30712345671" }));

    expect(respuesta.status).toBe(409);
    expect(await respuesta.json()).toEqual({
      error: "ClienteDuplicado",
      detalle: "Ya existe un cliente con ese CUIT.",
    });
  });

  it("un 409 de CUIT duplicado también reenvía el id del cliente existente", async () => {
    // HU-E4-01 — sin este campo el panel no puede «ofrecer ver el duplicado».
    cookieDeSesion = "un-access-token";
    llamarApi.mockRejectedValue(
      new ErrorDeApi(409, "Ya existe un cliente con ese CUIT.", "ClienteDuplicado", {
        cliente_existente_id: "c-1",
      }),
    );

    const respuesta = await postCliente(pedido({ nombre: "Rosa", cuit: "30712345671" }));

    expect(respuesta.status).toBe(409);
    expect(await respuesta.json()).toEqual({
      error: "ClienteDuplicado",
      detalle: "Ya existe un cliente con ese CUIT.",
      cliente_existente_id: "c-1",
    });
  });

  it("un cuerpo que no es JSON no rompe la ruta", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue(CLIENTE);

    const roto = new Request("http://test/api/clientes", { method: "POST", body: "{" });
    const respuesta = await postCliente(roto);

    expect(respuesta.status).toBe(200);
    expect(llamarApi).toHaveBeenCalledWith("/clientes", { method: "POST", body: {} });
  });
});
