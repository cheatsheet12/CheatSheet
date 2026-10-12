/**
 * `GET /api/planillas/google/callback` — la vuelta desde Google (HU-E2-04).
 *
 * En Render el panel escucha en `localhost:10000`, así que una redirección armada con
 * `request.url` mandaba a la persona a `https://localhost:10000/ingesta` (staging,
 * 11/10/2026). La vuelta tiene que salir siempre por la dirección pública del panel.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

let haySesionActiva = true;
const almacen = new Map<string, string>();

vi.mock("next/headers", () => ({
  cookies: () => ({
    get: (nombre: string) =>
      almacen.has(nombre) ? { name: nombre, value: almacen.get(nombre) } : undefined,
  }),
}));

vi.mock("@/lib/session", () => ({ haySesion: () => haySesionActiva }));

const llamarApi = vi.fn();
vi.mock("@/lib/api", async () => {
  const real = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...real, llamarApi: (...args: unknown[]) => llamarApi(...args) };
});

const { GET } = await import("@/app/api/planillas/google/callback/route");

afterEach(() => {
  haySesionActiva = true;
  almacen.clear();
  llamarApi.mockReset();
  vi.unstubAllEnvs();
});

describe("GET /api/planillas/google/callback", () => {
  it("envía al backend la dirección de escritura elegida", async () => {
    vi.stubEnv("APP_BASE_URL", "https://panel.ejemplo.test");
    almacen.set("planilla_oauth_state", "abc");
    almacen.set("planilla_oauth_documento", "sheet-123");
    almacen.set("planilla_oauth_direccion", "LECTURA_Y_ESCRITURA");
    llamarApi.mockResolvedValue({ id: "v1" });

    const respuesta = await GET(
      new Request(
        "https://panel.ejemplo.test/api/planillas/google/callback?code=code-123&state=abc",
      ),
    );

    expect(respuesta.headers.get("location")).toBe("https://panel.ejemplo.test/ingesta");
    expect(llamarApi).toHaveBeenCalledWith(
      "/planillas/google",
      expect.objectContaining({
        body: expect.objectContaining({
          identificador_documento: "sheet-123",
          direccion: "LECTURA_Y_ESCRITURA",
        }),
      }),
    );
  });
  it("sin el código de Google vuelve a Ingesta por la dirección pública", async () => {
    vi.stubEnv("APP_BASE_URL", "https://panel.ejemplo.test");

    const respuesta = await GET(
      new Request("https://localhost:10000/api/planillas/google/callback"),
    );

    const destino = new URL(respuesta.headers.get("location") ?? "");
    expect(destino.origin).toBe("https://panel.ejemplo.test");
    expect(destino.pathname).toBe("/ingesta");
    expect(destino.searchParams.get("error")).toBe("No se completó la vinculación con Google.");
  });

  it("sin sesión va al inicio por la dirección pública", async () => {
    vi.stubEnv("APP_BASE_URL", "https://panel.ejemplo.test");
    haySesionActiva = false;

    const respuesta = await GET(
      new Request("https://localhost:10000/api/planillas/google/callback"),
    );

    expect(respuesta.headers.get("location")).toBe("https://panel.ejemplo.test/");
  });
});
