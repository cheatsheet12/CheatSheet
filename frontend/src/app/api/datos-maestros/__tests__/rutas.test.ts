/**
 * La frontera del BFF para la corrección de datos existentes.
 *
 * Dos propiedades: ninguna ruta llega al backend sin sesión, y cada una reenvía al camino
 * exacto del router de `correccion.py` — incluido el `corrida_id` de la restauración.
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

const { GET: getInforme } = await import("@/app/api/datos-maestros/correccion/informe/route");
const { POST: postAplicar } = await import("@/app/api/datos-maestros/correccion/route");
const { GET: getCorridas } = await import("@/app/api/datos-maestros/correccion/corridas/route");
const { POST: postRestauracion } = await import(
  "@/app/api/datos-maestros/correccion/corridas/[corridaId]/restauracion/route"
);

const pedido = (): Request => new Request("http://test/api/datos-maestros/correccion");

afterEach(() => {
  cookieDeSesion = undefined;
  llamarApi.mockReset();
});

describe("sin sesión", () => {
  it("ninguna ruta llega al backend", async () => {
    const respuestas = await Promise.all([
      getInforme(),
      postAplicar(),
      getCorridas(),
      postRestauracion(pedido(), { params: { corridaId: "c-1" } }),
    ]);

    expect(respuestas.map((respuesta) => respuesta.status)).toEqual([401, 401, 401, 401]);
    expect(llamarApi).not.toHaveBeenCalled();
  });
});

describe("con sesión", () => {
  it("reenvía cada operación a su camino del backend", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({});

    await getInforme();
    await postAplicar();
    await getCorridas();
    await postRestauracion(pedido(), { params: { corridaId: "c-1" } });

    expect(llamarApi.mock.calls).toEqual([
      ["/datos-maestros/correccion/informe", { method: "GET" }],
      ["/datos-maestros/correccion", { method: "POST" }],
      ["/datos-maestros/correccion/corridas", { method: "GET" }],
      ["/datos-maestros/correccion/c-1/restauracion", { method: "POST" }],
    ]);
  });
});
