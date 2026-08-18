/**
 * The session cookie.
 *
 * These assertions are security properties, not preferences: a token readable from
 * JavaScript, or sent on a cross-site request, is the difference between a stolen
 * session and none (ADR-011).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const almacen = new Map<string, string>();
const set = vi.fn();
const borrar = vi.fn();

vi.mock("next/headers", () => ({
  cookies: () => ({
    get: (nombre: string) => {
      const value = almacen.get(nombre);
      return value === undefined ? undefined : { name: nombre, value };
    },
    set,
    delete: borrar,
  }),
}));

const { SESSION_COOKIE_NAME, cerrarSesion, guardarSesion, haySesion, leerClaims, leerToken } =
  await import("@/lib/session");

beforeEach(() => {
  almacen.clear();
  set.mockClear();
  borrar.mockClear();
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("sesión", () => {
  it("sin cookie no hay sesión", () => {
    expect(leerToken()).toBeUndefined();
    expect(haySesion()).toBe(false);
  });

  it("con cookie hay sesión", () => {
    almacen.set(SESSION_COOKIE_NAME, "fake-token-for-tests");

    expect(haySesion()).toBe(true);
    expect(leerToken()).toBe("fake-token-for-tests");
  });

  it("la cookie se escribe HttpOnly y SameSite=Lax", () => {
    guardarSesion({ token: "fake-token-for-tests" });

    const opciones = set.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(opciones.httpOnly).toBe(true);
    expect(opciones.sameSite).toBe("lax");
    expect(opciones.path).toBe("/");
  });

  it("la cookie es Secure en producción", () => {
    vi.stubEnv("NODE_ENV", "production");

    guardarSesion({ token: "fake-token-for-tests" });

    const opciones = set.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(opciones.secure).toBe(true);
  });

  it("el acceso vive poco: la renovación es del refresh token", () => {
    guardarSesion({ token: "fake-token-for-tests" });

    const opciones = set.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(opciones.maxAge).toBeLessThanOrEqual(15 * 60);
  });

  it("cerrar sesión borra la cookie", () => {
    cerrarSesion();

    expect(borrar).toHaveBeenCalledWith(SESSION_COOKIE_NAME);
  });
});

describe("leerClaims", () => {
  /** A JWT-shaped string. The signature is never checked here, so it is a placeholder. */
  function token(carga: Record<string, unknown>): string {
    const cuerpo = Buffer.from(JSON.stringify(carga)).toString("base64url");
    return `cabecera.${cuerpo}.firma-que-nadie-verifica-de-este-lado`;
  }

  it("devuelve el usuario, la empresa y el rol del access token", () => {
    almacen.set(
      SESSION_COOKIE_NAME,
      token({ sub: "u-1", empresa_id: "e-1", rol: "ADMINISTRADOR" }),
    );

    expect(leerClaims()).toEqual({
      usuarioId: "u-1",
      empresaId: "e-1",
      rol: "ADMINISTRADOR",
    });
  });

  it("sin cookie no hay claims", () => {
    expect(leerClaims()).toBeNull();
  });

  it("una cookie que no tiene forma de JWT no rompe nada", () => {
    almacen.set(SESSION_COOKIE_NAME, "no-es-un-jwt");

    expect(leerClaims()).toBeNull();
  });

  it("un cuerpo que no es JSON tampoco", () => {
    almacen.set(SESSION_COOKIE_NAME, "cabecera.bm8tZXMtanNvbg.firma");

    expect(leerClaims()).toBeNull();
  });

  it("un token sin sub ni empresa se trata como si no hubiera sesión", () => {
    // Not "half a session": either the panel knows who is looking, or it does not.
    almacen.set(SESSION_COOKIE_NAME, token({ rol: "OPERADOR" }));

    expect(leerClaims()).toBeNull();
  });
});
