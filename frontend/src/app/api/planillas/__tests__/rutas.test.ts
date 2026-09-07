/**
 * La frontera del BFF para las planillas (HU-E2-04, HU-E3-03).
 *
 * Además de la propiedad de siempre —ninguna ruta llega al backend sin sesión— este
 * archivo fija dos que son propias de la unidad:
 *
 * - **La subida es binaria**, la única de la aplicación. Va por `subirBinario` y no por
 *   `llamarApi`, y el nombre viaja codificado en la query porque los nombres en español
 *   traen acentos.
 * - **Un 422 llega con su `detalle` hasta el navegador.** HU-E3-03 escribe sus rechazos
 *   palabra por palabra, así que si el texto se pierde en el camino el criterio de
 *   aceptación queda incumplido — que es exactamente lo que le pasó a `ClienteDuplicado`
 *   en el épico 3 (`TODO.md` §10).
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
const subirBinario = vi.fn();
vi.mock("@/lib/api", async () => {
  const real = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...real,
    llamarApi: (...args: unknown[]) => llamarApi(...args),
    subirBinario: (...args: unknown[]) => subirBinario(...args),
  };
});

const { ErrorDeApi } = await import("@/lib/api");
const { GET: getPlanillas } = await import("@/app/api/planillas/route");
const { POST: postArchivo } = await import("@/app/api/planillas/archivo/route");
const { DELETE: deletePlanilla } = await import("@/app/api/planillas/[vinculoId]/route");
const { POST: postAutorizacion } = await import(
  "@/app/api/planillas/google/autorizacion/route"
);
const { POST: postGoogle } = await import("@/app/api/planillas/google/route");
const { POST: postMapeo } = await import("@/app/api/planillas/mapeos/route");
const { PUT: putColumna } = await import(
  "@/app/api/planillas/mapeos/[mapeoId]/columnas/route"
);
const { POST: postConfirmacion } = await import(
  "@/app/api/planillas/mapeos/[mapeoId]/confirmacion/route"
);

const MAPEO_ID = "3f1c2b8e-0000-4000-8000-000000000050";

function pedidoJson(cuerpo: unknown): Request {
  return new Request("http://localhost/x", { method: "POST", body: JSON.stringify(cuerpo) });
}

const VINCULO_ID = "3f1c2b8e-0000-4000-8000-000000000040";

function pedidoDeSubida(nombre: string, cuerpo = "bytes"): Request {
  return new Request(`http://localhost/api/planillas/archivo?nombre=${encodeURIComponent(nombre)}`, {
    method: "POST",
    body: cuerpo,
  });
}

afterEach(() => {
  cookieDeSesion = undefined;
  vi.clearAllMocks();
});

describe("sin sesion", () => {
  it("ninguna ruta llega al backend", async () => {
    const respuestas = await Promise.all([
      getPlanillas(),
      postAutorizacion(),
      postGoogle(new Request("http://localhost/api/planillas/google", { method: "POST" })),
      postArchivo(pedidoDeSubida("clientes.xlsx")),
      postMapeo(new Request("http://localhost/x", { method: "POST", body: "{}" })),
      deletePlanilla(new Request("http://localhost"), { params: { vinculoId: VINCULO_ID } }),
    ]);

    for (const respuesta of respuestas) {
      expect(respuesta.status).toBe(401);
    }
    expect(llamarApi).not.toHaveBeenCalled();
    expect(subirBinario).not.toHaveBeenCalled();
  });
});

describe("con sesion", () => {
  it("lista las planillas", async () => {
    cookieDeSesion = "token";
    llamarApi.mockResolvedValue({ vinculos: [] });

    const respuesta = await getPlanillas();

    expect(llamarApi).toHaveBeenCalledWith("/planillas", { method: "GET" });
    expect(await respuesta.json()).toEqual({ vinculos: [] });
  });

  it("desvincula por id", async () => {
    cookieDeSesion = "token";
    llamarApi.mockResolvedValue({});

    await deletePlanilla(new Request("http://localhost"), { params: { vinculoId: VINCULO_ID } });

    expect(llamarApi).toHaveBeenCalledWith(`/planillas/${VINCULO_ID}`, { method: "DELETE" });
  });

  it("manda los bytes por el camino binario y codifica el nombre", async () => {
    cookieDeSesion = "token";
    subirBinario.mockResolvedValue({ id: VINCULO_ID });

    const respuesta = await postArchivo(pedidoDeSubida("clientes año.xlsx"));

    expect(respuesta.status).toBe(201);
    const [ruta] = subirBinario.mock.calls[0] as [string];
    expect(ruta).toBe("/planillas/archivo?nombre=clientes%20a%C3%B1o.xlsx");
    // La subida no pasa por el camino JSON: ese fija `Content-Type: application/json`.
    expect(llamarApi).not.toHaveBeenCalled();
  });

  it("rechaza una subida sin nombre antes de tocar el backend", async () => {
    cookieDeSesion = "token";

    const respuesta = await postArchivo(
      new Request("http://localhost/api/planillas/archivo", { method: "POST", body: "x" }),
    );

    expect(respuesta.status).toBe(422);
    expect(subirBinario).not.toHaveBeenCalled();
  });

  it("deja pasar el detalle de un 422 hasta el navegador", async () => {
    cookieDeSesion = "token";
    subirBinario.mockRejectedValue(
      new ErrorDeApi(422, "Formato no aceptado. Use .xlsx, .xls o .csv.", "FormatoDePlanillaNoSoportado"),
    );

    const respuesta = await postArchivo(pedidoDeSubida("clientes.pdf"));

    expect(respuesta.status).toBe(422);
    // El codigo **y** el texto. Sin el texto, la pantalla muestra un mensaje generico y
    // el criterio de aceptacion de HU-E3-03 queda incumplido de punta a punta.
    expect(await respuesta.json()).toEqual({
      error: "FormatoDePlanillaNoSoportado",
      detalle: "Formato no aceptado. Use .xlsx, .xls o .csv.",
    });
  });

  it("no filtra el detalle de un 409", async () => {
    cookieDeSesion = "token";
    llamarApi.mockRejectedValue(
      new ErrorDeApi(409, "detalle interno para un log", "InvarianteViolada"),
    );

    const respuesta = await postGoogle(
      new Request("http://localhost/api/planillas/google", {
        method: "POST",
        body: JSON.stringify({ codigo: "c", identificador_documento: "d", estado: "e" }),
      }),
    );

    expect(respuesta.status).toBe(409);
    expect(await respuesta.json()).toEqual({ error: "InvarianteViolada" });
  });

  it("propone, corrige y confirma un mapeo", async () => {
    cookieDeSesion = "token";
    llamarApi.mockResolvedValue({ id: MAPEO_ID, faltantes: [] });

    await postMapeo(pedidoJson({ vinculo_id: "v1", columnas: [{ nombre: "CUIT" }] }));
    await putColumna(pedidoJson({ columna: "CUIT", atributo: "cuit" }), {
      params: { mapeoId: MAPEO_ID },
    });
    await postConfirmacion(pedidoJson({}), { params: { mapeoId: MAPEO_ID } });

    const rutas = llamarApi.mock.calls.map(([ruta]) => ruta as string);
    expect(rutas).toEqual([
      "/planillas/mapeos",
      `/planillas/mapeos/${MAPEO_ID}/columnas`,
      `/planillas/mapeos/${MAPEO_ID}/confirmacion`,
    ]);
  });

  it("pide la url de autorizacion de Google", async () => {
    cookieDeSesion = "token";
    llamarApi.mockResolvedValue({ url: "https://accounts.google.com/o/oauth2/v2/auth?x=1" });

    const respuesta = await postAutorizacion();

    expect(llamarApi).toHaveBeenCalledWith("/planillas/google/autorizacion", { method: "POST" });
    expect(await respuesta.json()).toEqual({
      url: "https://accounts.google.com/o/oauth2/v2/auth?x=1",
    });
  });
});
