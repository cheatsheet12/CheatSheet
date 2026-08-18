/**
 * The BFF boundary.
 *
 * The property under test is not "does it proxy" — it is what the browser is *not*
 * told. The backend's URL and the reason it failed stay on the server; the client
 * gets a status and a flag. Every future feature route inherits this shape.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "@/app/api/health/route";
import { ErrorDeApi } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const real = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...real, llamarApi: vi.fn() };
});

const { llamarApi } = await import("@/lib/api");

afterEach(() => {
  vi.mocked(llamarApi).mockReset();
});

describe("GET /api/health", () => {
  it("devuelve el estado del backend sin exponer su URL", async () => {
    vi.mocked(llamarApi).mockResolvedValue({
      estado: "ok",
      base_de_datos: true,
      redis: true,
    });

    const respuesta = await GET();
    const cuerpo: unknown = await respuesta.json();

    expect(respuesta.status).toBe(200);
    expect(cuerpo).toEqual({ estado: "ok", api: true });
    expect(JSON.stringify(cuerpo)).not.toContain("http");
  });

  it("responde 503 cuando la API no contesta, sin filtrar el motivo", async () => {
    vi.mocked(llamarApi).mockRejectedValue(new ErrorDeApi(504, "La API no respondió en 3000 ms"));

    const respuesta = await GET();
    const cuerpo: unknown = await respuesta.json();

    expect(respuesta.status).toBe(503);
    expect(cuerpo).toEqual({ estado: "degradado", api: false });
  });
});
