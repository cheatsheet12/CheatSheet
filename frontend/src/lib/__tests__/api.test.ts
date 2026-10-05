/**
 * The fetch wrapper: the two behaviours that are easy to leave out and expensive to
 * discover in production — the timeout, and not leaking the backend's internals.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ErrorDeApi, llamarApi } from "@/lib/api";

/** Named so it cannot be mistaken for a credential, by a person or by the guard. */
const FAKE_TOKEN_FOR_TESTS = "fake-token-for-tests";

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

  it("el barril de lib expone la misma puerta", async () => {
    const barril = await import("@/lib");

    expect(barril.llamarApi).toBeTypeOf("function");
    expect(barril.ErrorDeApi).toBeTypeOf("function");
  });
});
