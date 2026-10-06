/**
 * Deleting an FAQ end to end through the BFF, with the REAL `llamarApi`.
 *
 * The backend answers `204 No Content` (empty body). The route tests elsewhere mock
 * `llamarApi` whole and make it return `{}`, so the seam between `fetch` and the body
 * parsing was never exercised — which is how a delete that worked looked like an error.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/headers", () => ({
  cookies: () => ({
    get: (nombre: string) =>
      nombre === "cheatsheet_session" ? { name: nombre, value: "un-access-token" } : undefined,
    set: () => undefined,
    delete: () => undefined,
  }),
}));

const rutaFaq = await import("@/app/api/faqs/[faqId]/route");

describe("DELETE /api/faqs/[faqId]", () => {
  beforeEach(() => {
    vi.stubEnv("BACKEND_API_URL", "http://api.interno:8000");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("answers 200 {} when the backend deletes with a 204 and no body", async () => {
    const fetchFalso = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchFalso);

    const respuesta = await rutaFaq.DELETE(
      new Request("http://test/api/faqs/f1", { method: "DELETE" }),
      { params: { faqId: "f1" } },
    );

    expect(respuesta.status).toBe(200);
    expect(await respuesta.json()).toEqual({});
    const [url, opciones] = fetchFalso.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api.interno:8000/faqs/f1");
    expect(opciones.method).toBe("DELETE");
  });
});
