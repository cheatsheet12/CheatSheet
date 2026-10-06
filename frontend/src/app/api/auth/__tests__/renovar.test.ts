/**
 * `GET /api/auth/renovar` — the hop a page navigation takes when the access cookie is gone.
 *
 * Two things are at stake: that a person with a live refresh token never meets the login
 * just because fifteen minutes went by, and that the `destino` parameter cannot be turned
 * into an open redirect.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

const cookiesBorradas: string[] = [];
const almacen = new Map<string, string>();

vi.mock("next/headers", () => ({
  cookies: () => ({
    get: (nombre: string) =>
      almacen.has(nombre) ? { name: nombre, value: almacen.get(nombre) } : undefined,
    set: (opciones: Record<string, unknown>) => {
      almacen.set(String(opciones.name), String(opciones.value));
    },
    delete: (nombre: string) => {
      cookiesBorradas.push(nombre);
      almacen.delete(nombre);
    },
  }),
}));

const llamarApi = vi.fn();
vi.mock("@/lib/api", async () => {
  const real = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...real, llamarApi: (...args: unknown[]) => llamarApi(...args) };
});

const { ErrorDeApi } = await import("@/lib/api");
const { GET } = await import("@/app/api/auth/renovar/route");
const { destinoSeguro } = await import("@/app/api/auth/_sesion");

const SESION = {
  access_token: "access-nuevo",
  refresh_token: "refresh-nuevo",
  empresa_id: "3f1c2b8e-0000-4000-8000-000000000001",
  usuario_id: "3f1c2b8e-0000-4000-8000-000000000002",
  onboarding_completo: true,
};

function pedido(destino?: string): Request {
  const url = new URL("http://panel.test/api/auth/renovar");
  if (destino !== undefined) {
    url.searchParams.set("destino", destino);
  }
  return new Request(url);
}

function ubicacion(respuesta: Response): string {
  return new URL(respuesta.headers.get("location") ?? "").pathname;
}

afterEach(() => {
  cookiesBorradas.length = 0;
  almacen.clear();
  llamarApi.mockReset();
});

describe("GET /api/auth/renovar", () => {
  it("con refresh vigente renueva las dos cookies y entra al panel", async () => {
    almacen.set("cheatsheet_refresh", "refresh-viejo");
    llamarApi.mockResolvedValue(SESION);

    const respuesta = await GET(pedido());

    expect(ubicacion(respuesta)).toBe("/panel");
    expect(almacen.get("cheatsheet_session")).toBe("access-nuevo");
    expect(almacen.get("cheatsheet_refresh")).toBe("refresh-nuevo");
  });

  it("vuelve a la pantalla de la que venía", async () => {
    almacen.set("cheatsheet_refresh", "refresh-viejo");
    llamarApi.mockResolvedValue(SESION);

    const respuesta = await GET(pedido("/cobros"));

    expect(ubicacion(respuesta)).toBe("/cobros");
  });

  it("sin refresh va al login sin llamar al backend", async () => {
    const respuesta = await GET(pedido());

    expect(ubicacion(respuesta)).toBe("/");
    expect(llamarApi).not.toHaveBeenCalled();
  });

  it("un refresh rechazado limpia las dos cookies y va al login", async () => {
    almacen.set("cheatsheet_refresh", "refresh-revocado");
    llamarApi.mockRejectedValue(new ErrorDeApi(401, "revocado", "SesionInvalida"));

    const respuesta = await GET(pedido("/cobros"));

    expect(ubicacion(respuesta)).toBe("/");
    expect(cookiesBorradas).toEqual(
      expect.arrayContaining(["cheatsheet_session", "cheatsheet_refresh"]),
    );
  });

  it("una empresa sin onboarding vuelve al onboarding", async () => {
    almacen.set("cheatsheet_refresh", "refresh-viejo");
    llamarApi.mockResolvedValue({ ...SESION, onboarding_completo: false });

    const respuesta = await GET(pedido("/cobros"));

    expect(ubicacion(respuesta)).toBe("/onboarding/empresa");
  });
});

describe("destinoSeguro", () => {
  it.each([
    [null, "/panel"],
    ["/cobros", "/cobros"],
    ["https://otro.test/robar", "/panel"],
    ["//otro.test", "/panel"],
    ["/\\otro.test", "/panel"],
    ["/api/auth/logout", "/panel"],
    ["cobros", "/panel"],
  ])("%s → %s", (destino, esperado) => {
    expect(destinoSeguro(destino)).toBe(esperado);
  });
});
