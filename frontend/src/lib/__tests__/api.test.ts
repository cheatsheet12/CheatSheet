/**
 * The fetch wrapper: the two behaviours that are easy to leave out and expensive to
 * discover in production — the timeout, and not leaking the backend's internals.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { comoRutaDelBff, ErrorDeApi, llamarApi } from "@/lib/api";

/** Named so it cannot be mistaken for a credential, by a person or by the guard. */
const FAKE_TOKEN_FOR_TESTS = "fake-token-for-tests";

const redirect = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({ redirect }));

vi.mock("@/lib/session", () => ({
  leerToken: (): string | undefined => "fake-token-for-tests",
}));

describe("llamarApi", () => {
  beforeEach(() => {
    vi.stubEnv("BACKEND_API_URL", "http://api.interno:8000");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("adjunta el token de la cookie sin exponerlo al cliente", async () => {
    const fetchFalso = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ estado: "ok" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchFalso);

    await llamarApi<{ estado: string }>("/health");

    const [, opciones] = fetchFalso.mock.calls[0] as [string, RequestInit];
    const headers = opciones.headers as Record<string, string>;
    expect(headers.Authorization).toBe(`Bearer ${FAKE_TOKEN_FOR_TESTS}`);
  });

  it("corta por timeout y no queda esperando para siempre", async () => {
    vi.stubGlobal(
      "fetch",
      (_url: string, opciones: RequestInit) =>
        new Promise((_resolver, rechazar) => {
          opciones.signal?.addEventListener("abort", () => {
            rechazar(new DOMException("abortada", "AbortError"));
          });
        }),
    );

    await expect(llamarApi("/health", { timeoutMs: 10 })).rejects.toBeInstanceOf(ErrorDeApi);
  });

  it("traduce un error de la API a un valor tipado", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ detalle: "CUIT invalido" }), { status: 422 }),
        ),
    );

    await expect(llamarApi("/empresas")).rejects.toMatchObject({
      status: 422,
      detalle: "CUIT invalido",
    });
  });

  it("falla claro cuando falta la URL del backend", async () => {
    vi.stubEnv("BACKEND_API_URL", "");

    await expect(llamarApi("/health")).rejects.toThrow("BACKEND_API_URL");
  });

  it("cae al statusText cuando el error no trae cuerpo JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("<html>502</html>", {
          status: 502,
          statusText: "Bad Gateway",
        }),
      ),
    );

    await expect(llamarApi("/health")).rejects.toMatchObject({
      status: 502,
      detalle: "Bad Gateway",
    });
  });

  it("cae al statusText cuando el JSON de error no tiene detalle", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ otra_cosa: 1 }), { status: 500, statusText: "Error" }),
        ),
    );

    await expect(llamarApi("/health")).rejects.toMatchObject({ detalle: "Error" });
  });

  it("conserva los campos del 409 que no son detalle ni error, como cliente_existente_id", async () => {
    // HU-E4-01 pide «ofrecer ver el duplicado»: el 409 de `ClienteDuplicado` manda un tercer
    // campo, `cliente_existente_id`, además de `error` y `detalle`. Si se descarta acá, no hay
    // forma de que el botón llegue a mostrarse, sin importar lo que haga el resto del camino.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: "ClienteDuplicado",
            detalle: "Ya existe un cliente con ese CUIT.",
            cliente_existente_id: "c-1",
          }),
          { status: 409 },
        ),
      ),
    );

    await expect(llamarApi("/clientes")).rejects.toMatchObject({
      status: 409,
      detalle: "Ya existe un cliente con ese CUIT.",
      extra: { cliente_existente_id: "c-1" },
    });
  });

  it("sin campos extra, extra queda vacío", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ detalle: "CUIT invalido" }), { status: 422 }),
        ),
    );

    await expect(llamarApi("/empresas")).rejects.toMatchObject({ extra: {} });
  });

  it("envía el cuerpo serializado en un POST", async () => {
    const fetchFalso = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchFalso);

    await llamarApi("/empresas", { method: "POST", body: { cuit: "30-11111111-1" } });

    const [, opciones] = fetchFalso.mock.calls[0] as [string, RequestInit];
    expect(opciones.method).toBe("POST");
    expect(opciones.body).toBe(JSON.stringify({ cuit: "30-11111111-1" }));
  });

  it("resuelve a undefined cuando la API contesta 204 sin cuerpo", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));

    await expect(llamarApi<unknown>("/faqs/f1", { method: "DELETE" })).resolves.toBeUndefined();
  });

  it("resuelve a undefined cuando un 200 llega con el cuerpo vacío", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 200 })));

    await expect(llamarApi<unknown>("/health")).resolves.toBeUndefined();
  });

  it("sigue devolviendo el objeto parseado cuando el 200 trae JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ estado: "ok" }), { status: 200 })),
    );

    await expect(llamarApi<{ estado: string }>("/health")).resolves.toEqual({ estado: "ok" });
  });

  it("sin opción de revalidación no cachea, como hasta ahora", async () => {
    const fetchFalso = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchFalso);

    await llamarApi("/health");

    const [, opciones] = fetchFalso.mock.calls[0] as [string, RequestInit & { next?: unknown }];
    expect(opciones.cache).toBe("no-store");
    expect(opciones.next).toBeUndefined();
  });

  it("con revalidarCadaSegundos pide a Next revalidar en vez de no cachear", async () => {
    const fetchFalso = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchFalso);

    await llamarApi("/legal/privacidad", { revalidarCadaSegundos: 3600 });

    const [, opciones] = fetchFalso.mock.calls[0] as [string, RequestInit & { next?: unknown }];
    expect(opciones.next).toEqual({ revalidate: 3600 });
    expect(opciones.cache).toBeUndefined();
  });

  describe("bloqueo por aceptación legal pendiente", () => {
    const bloqueo = (status: number, error: string): Response =>
      new Response(JSON.stringify({ error, detalle: "x" }), { status });

    beforeEach(() => {
      redirect.mockReset();
      redirect.mockImplementation((destino: string) => {
        throw new Error(`NEXT_REDIRECT:${destino}`);
      });
    });

    it("una página de servidor va a /aceptacion-legal ante un 403 AceptacionLegalPendiente", async () => {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(bloqueo(403, "AceptacionLegalPendiente")));

      await expect(llamarApi("/cobros")).rejects.toThrow("NEXT_REDIRECT:/aceptacion-legal");
      expect(redirect).toHaveBeenCalledWith("/aceptacion-legal");
    });

    it("una ruta del BFF recibe el ErrorDeApi, sin redirigir", async () => {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(bloqueo(403, "AceptacionLegalPendiente")));

      await expect(comoRutaDelBff(() => llamarApi("/cobros"))).rejects.toMatchObject({
        status: 403,
        codigo: "AceptacionLegalPendiente",
      });
      expect(redirect).not.toHaveBeenCalled();
    });

    it("cualquier otro 403 sigue siendo un ErrorDeApi", async () => {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(bloqueo(403, "RolInsuficiente")));

      await expect(llamarApi("/usuarios")).rejects.toMatchObject({
        status: 403,
        codigo: "RolInsuficiente",
      });
      expect(redirect).not.toHaveBeenCalled();
    });

    it("el mismo código con otro estado no redirige", async () => {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(bloqueo(409, "AceptacionLegalPendiente")));

      await expect(llamarApi("/usuarios")).rejects.toBeInstanceOf(ErrorDeApi);
      expect(redirect).not.toHaveBeenCalled();
    });
  });

  it("el barril de lib expone la misma puerta", async () => {
    const barril = await import("@/lib");

    expect(barril.llamarApi).toBeTypeOf("function");
    expect(barril.ErrorDeApi).toBeTypeOf("function");
  });
});
