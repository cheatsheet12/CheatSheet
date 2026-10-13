/**
 * The BFF keeps the JSON 403 when a legal document is pending (HU-E1-03 RN-03).
 *
 * Unlike the other route tests this one does **not** mock `llamarApi`: the property under test
 * is how the real wrapper behaves when the proxy calls it. A server page redirects on that 403;
 * a route handler must answer it as data, because its caller is `VigilanteDeAceptacionLegal`.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const redirect = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({ redirect }));

vi.mock("next/headers", () => ({
  cookies: () => ({
    get: (nombre: string) =>
      nombre === "cheatsheet_session" ? { name: nombre, value: "fake-token-for-tests" } : undefined,
    set: () => undefined,
    delete: () => undefined,
  }),
}));

const { GET: getUsuarios } = await import("@/app/api/usuarios/route");

describe("el proxy del BFF ante una aceptación legal pendiente", () => {
  beforeEach(() => {
    vi.stubEnv("BACKEND_API_URL", "http://api.interno:8000");
    redirect.mockImplementation((destino: string) => {
      throw new Error(`NEXT_REDIRECT:${destino}`);
    });
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    redirect.mockReset();
  });

  it("responde el 403 con su código y no redirige", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({ error: "AceptacionLegalPendiente", detalle: "x", pendientes: [] }),
            { status: 403 },
          ),
        ),
    );

    const respuesta = await getUsuarios();

    expect(respuesta.status).toBe(403);
    expect(await respuesta.json()).toEqual({ error: "AceptacionLegalPendiente" });
    expect(redirect).not.toHaveBeenCalled();
  });
});
