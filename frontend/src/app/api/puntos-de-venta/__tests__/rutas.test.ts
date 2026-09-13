/**
 * La frontera del BFF para los puntos de venta.
 *
 * Dos propiedades, las mismas que en el resto del panel: **ninguna ruta llega al backend
 * sin sesión**, y el `detalle` de un 422 cruza entero. Lo segundo importa más acá que en
 * ningún otro lado del sistema: las dos frases que HU-E5-05 escribe —«El punto de venta
 * no está habilitado en ARCA.» y «Ya existe un punto de venta con ese número.»— son
 * mensajes del sistema pensados para el usuario, y si el BFF se los come, la pantalla
 * tiene que inventar un texto peor.
 *
 * Y una tercera, por omisión: **no hay `DELETE`**. El backend no tiene el permiso, así que
 * una ruta acá sólo podría fallar.
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
const rutaBase = await import("@/app/api/puntos-de-venta/route");
const rutaEstado = await import("@/app/api/puntos-de-venta/[puntoId]/estado/route");

const PUNTO = {
  id: "3f1c2b8e-0000-4000-8000-000000000050",
  numero: 1,
  descripcion: "Casa central",
  activo: true,
  numerador_por_tipo: { FACTURA_B: 12 },
  created_at: "2026-09-07T12:00:00Z",
};

function pedido(cuerpo: unknown = {}): Request {
  return new Request("http://test/api/puntos-de-venta", {
    method: "POST",
    body: JSON.stringify(cuerpo),
  });
}

afterEach(() => {
  cookieDeSesion = undefined;
  llamarApi.mockReset();
});

describe("sin sesión", () => {
  it("ninguna ruta llega al backend", async () => {
    const respuestas = await Promise.all([
      rutaBase.GET(),
      rutaBase.POST(pedido({ numero: 1 })),
      rutaEstado.PUT(pedido({ activo: false }), { params: { puntoId: "un-punto" } }),
    ]);

    expect(respuestas.map((respuesta) => respuesta.status)).toEqual([401, 401, 401]);
    expect(llamarApi).not.toHaveBeenCalled();
  });
});

describe("con sesión", () => {
  it("lista los puntos de la empresa", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ puntos: [PUNTO] });

    const respuesta = await rutaBase.GET();

    expect(respuesta.status).toBe(200);
    expect(await respuesta.json()).toEqual({ puntos: [PUNTO] });
    expect(llamarApi).toHaveBeenCalledWith("/puntos-de-venta", { method: "GET" });
  });

  it("el cambio de estado usa el id de la ruta", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ ...PUNTO, activo: false });

    await rutaEstado.PUT(pedido({ activo: false }), { params: { puntoId: "p-1" } });

    expect(llamarApi).toHaveBeenCalledWith("/puntos-de-venta/p-1/estado", {
      method: "PUT",
      body: { activo: false },
    });
  });

  it("un 422 llega con la frase de la historia, que es la que se muestra", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockRejectedValue(
      new ErrorDeApi(422, "El punto de venta no está habilitado en ARCA.", "EntradaInvalida"),
    );

    const respuesta = await rutaBase.POST(pedido({ numero: 7 }));

    expect(respuesta.status).toBe(422);
    expect(await respuesta.json()).toEqual({
      error: "EntradaInvalida",
      detalle: "El punto de venta no está habilitado en ARCA.",
    });
  });

  it("un 503 no filtra el detalle: eso es internals, no un mensaje para el usuario", async () => {
    // ARCA caída no es lo mismo que ARCA diciendo que no, y el backend las mantiene
    // separadas. Del lado del BFF la diferencia se ve así: sólo el 422 lleva `detalle`.
    cookieDeSesion = "un-access-token";
    llamarApi.mockRejectedValue(
      new ErrorDeApi(503, "wsfe timeout tras 3 intentos", "ArcaNoDisponible"),
    );

    const respuesta = await rutaBase.POST(pedido({ numero: 1 }));

    expect(respuesta.status).toBe(503);
    expect(await respuesta.json()).toEqual({ error: "ArcaNoDisponible" });
  });
});

describe("lo que no existe", () => {
  it("no hay DELETE: el backend no tiene el permiso", () => {
    expect("DELETE" in rutaBase).toBe(false);
    expect("DELETE" in rutaEstado).toBe(false);
  });
});
