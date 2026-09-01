/**
 * La frontera del BFF para el catálogo de servicios.
 *
 * Las mismas dos propiedades que las rutas de clientes —ninguna llega al backend sin
 * sesión, y el query string se reenvía entero— más una que es de esta unidad: **el precio
 * cruza como texto**. El test lo fija porque el día que alguien lo convierta a `number`
 * "para que sea más prolijo", el error binario entra al sistema sin que nada falle.
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
const { GET: getServicios, POST: postServicio } = await import("@/app/api/servicios/route");
const { PUT: putServicio } = await import("@/app/api/servicios/[servicioId]/route");
const { PUT: putEstado } = await import("@/app/api/servicios/[servicioId]/estado/route");

const SERVICIO = {
  id: "3f1c2b8e-0000-4000-8000-000000000020",
  nombre: "Corte de pelo",
  precio: "5000.00",
  alicuota_iva: "0.21",
  agendable: true,
  duracion_estandar_min: 45,
  origen: "PANEL",
  activo: true,
};

function pedido(cuerpo: unknown = {}): Request {
  return new Request("http://test/api/servicios", {
    method: "POST",
    body: JSON.stringify(cuerpo),
  });
}

function listado(consulta = ""): Request {
  return new Request(`http://test/api/servicios${consulta}`, { method: "GET" });
}

afterEach(() => {
  cookieDeSesion = undefined;
  llamarApi.mockReset();
});

describe("sin sesión", () => {
  it("ninguna ruta llega al backend", async () => {
    const respuestas = await Promise.all([
      getServicios(listado()),
      postServicio(pedido({ nombre: "Corte" })),
      putServicio(pedido({ nombre: "Corte" }), { params: { servicioId: "un-servicio" } }),
      putEstado(pedido({ activo: false }), { params: { servicioId: "un-servicio" } }),
    ]);

    expect(respuestas.map((respuesta) => respuesta.status)).toEqual(Array(4).fill(401));
    expect(llamarApi).not.toHaveBeenCalled();
  });
});

describe("con sesión", () => {
  it("lista el catálogo de la empresa", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ servicios: [SERVICIO], total: 1 });

    const respuesta = await getServicios(listado());

    expect(respuesta.status).toBe(200);
    expect(await respuesta.json()).toEqual({ servicios: [SERVICIO], total: 1 });
    expect(llamarApi).toHaveBeenCalledWith("/servicios", { method: "GET" });
  });

  it("reenvía el query string entero, sin conocer los filtros", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ servicios: [], total: 0 });

    await getServicios(listado("?texto=corte&agendable=true&solo_activos=true"));

    expect(llamarApi).toHaveBeenCalledWith(
      "/servicios?texto=corte&agendable=true&solo_activos=true",
      { method: "GET" },
    );
  });

  it("el precio cruza como texto y no como numero", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue(SERVICIO);

    await postServicio(pedido({ nombre: "Corte", precio: "5000.00", alicuota_iva: "0.21" }));

    const [, opciones] = llamarApi.mock.calls[0] as [string, { body: { precio: unknown } }];
    expect(typeof opciones.body.precio).toBe("string");
    expect(opciones.body.precio).toBe("5000.00");
  });

  it("la edición y el cambio de estado usan el id de la ruta", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue(SERVICIO);

    await putServicio(pedido({ nombre: "Corte y barba" }), { params: { servicioId: "s-1" } });
    await putEstado(pedido({ activo: false }), { params: { servicioId: "s-1" } });

    expect(llamarApi).toHaveBeenNthCalledWith(1, "/servicios/s-1", {
      method: "PUT",
      body: { nombre: "Corte y barba" },
    });
    expect(llamarApi).toHaveBeenNthCalledWith(2, "/servicios/s-1/estado", {
      method: "PUT",
      body: { activo: false },
    });
  });

  it("un 422 llega con el mensaje, que es lo que la pantalla muestra", async () => {
    // `respuestaDeError` reenvía `detalle` **sólo** para `EntradaInvalida`, y esa
    // excepción es deliberada: los mensajes de HU-E4-02 —«El precio debe ser mayor a
    // cero.»— son textos del sistema pensados para el usuario. Para cualquier otro
    // código sólo viaja el nombre, que es lo que evita filtrar internals.
    cookieDeSesion = "un-access-token";
    llamarApi.mockRejectedValue(
      new ErrorDeApi(422, "El precio debe ser mayor a cero.", "EntradaInvalida"),
    );

    const respuesta = await postServicio(pedido({ nombre: "Corte", precio: "0" }));

    expect(respuesta.status).toBe(422);
    expect(await respuesta.json()).toEqual({
      error: "EntradaInvalida",
      detalle: "El precio debe ser mayor a cero.",
    });
  });

  it("un 403 llega sin detalle: sólo `EntradaInvalida` lo lleva", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockRejectedValue(
      new ErrorDeApi(403, "Se requiere rol Administrador u Operador", "PermisoDenegado"),
    );

    const respuesta = await postServicio(pedido({ nombre: "Corte" }));

    expect(respuesta.status).toBe(403);
    expect(await respuesta.json()).toEqual({ error: "PermisoDenegado" });
  });

  it("un cuerpo que no es JSON no rompe la ruta", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue(SERVICIO);

    const roto = new Request("http://test/api/servicios", { method: "POST", body: "{" });
    const respuesta = await postServicio(roto);

    expect(respuesta.status).toBe(200);
    expect(llamarApi).toHaveBeenCalledWith("/servicios", { method: "POST", body: {} });
  });
});
