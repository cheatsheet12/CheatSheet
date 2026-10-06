/**
 * The three handlers this unit added to `/api/auth`: Google, refresh and acceptance.
 *
 * The Google callback is the one that earns its tests. It is the only endpoint in the
 * system that acts on a request arriving from somebody else's domain, and the `state`
 * check is the entire defence: without it, anybody can hand a victim a callback URL
 * carrying the attacker's authorization code and quietly bind the victim's browser to the
 * attacker's account.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

const cookiesPuestas: Array<Record<string, unknown>> = [];
const cookiesBorradas: string[] = [];
const almacen = new Map<string, string>();

vi.mock("next/headers", () => ({
  cookies: () => ({
    get: (nombre: string) =>
      almacen.has(nombre) ? { name: nombre, value: almacen.get(nombre) } : undefined,
    set: (opciones: Record<string, unknown>) => {
      cookiesPuestas.push(opciones);
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
const { GET: getGoogle, COOKIE_STATE } = await import("@/app/api/auth/google/route");
const { GET: getCallback } = await import("@/app/api/auth/google/callback/route");
const { POST: postRefresh } = await import("@/app/api/auth/refresh/route");
const { POST: postAceptar } = await import("@/app/api/auth/invitaciones/aceptar/route");

const SESION = {
  access_token: "un-access-token",
  refresh_token: "un-refresh-token",
  empresa_id: "3f1c2b8e-0000-4000-8000-000000000001",
  usuario_id: "3f1c2b8e-0000-4000-8000-000000000002",
  onboarding_completo: false,
};

function callback(parametros: Record<string, string>): Request {
  const url = new URL("http://test/api/auth/google/callback");
  for (const [clave, valor] of Object.entries(parametros)) {
    url.searchParams.set(clave, valor);
  }
  return new Request(url);
}

function ubicacion(respuesta: Response): string {
  return respuesta.headers.get("location") ?? "";
}

afterEach(() => {
  cookiesPuestas.length = 0;
  cookiesBorradas.length = 0;
  almacen.clear();
  llamarApi.mockReset();
});

describe("GET /api/auth/google", () => {
  it("guarda el state y redirige a donde diga el backend", async () => {
    llamarApi.mockResolvedValue({ url: "https://accounts.google.com/o/oauth2/v2/auth?x=1" });

    const respuesta = await getGoogle();

    expect(respuesta.status).toBe(307);
    expect(ubicacion(respuesta)).toContain("accounts.google.com");
    const cookie = cookiesPuestas.find((puesta) => puesta.name === COOKIE_STATE);
    expect(cookie?.httpOnly).toBe(true);
    // `lax`, not `strict`: the browser returns here from Google's domain.
    expect(cookie?.sameSite).toBe("lax");
  });

  it("si el backend no tiene Google configurado, vuelve al inicio con el motivo", async () => {
    llamarApi.mockRejectedValue(new ErrorDeApi(409, "no configurado", "OAuthFallido"));

    const respuesta = await getGoogle();

    expect(ubicacion(respuesta)).toContain("error=OAuthFallido");
  });
});

describe("GET /api/auth/google/callback", () => {
  it("un state que no coincide se rechaza antes de gastar el código", async () => {
    almacen.set(COOKIE_STATE, "el-state-que-emitimos");

    const respuesta = await getCallback(
      callback({ state: "otro-state", code: "simulado:ana@empresa.com" }),
    );

    expect(ubicacion(respuesta)).toContain("error=OAuthStateInvalido");
    expect(llamarApi).not.toHaveBeenCalled();
  });

  it("sin cookie de state tampoco pasa", async () => {
    const respuesta = await getCallback(
      callback({ state: "cualquiera", code: "simulado:ana@empresa.com" }),
    );

    expect(ubicacion(respuesta)).toContain("error=OAuthStateInvalido");
    expect(llamarApi).not.toHaveBeenCalled();
  });

  it("quien cancela en Google vuelve sin que eso se reporte como falla", async () => {
    almacen.set(COOKIE_STATE, "el-state");

    const respuesta = await getCallback(callback({ state: "el-state", error: "access_denied" }));

    expect(ubicacion(respuesta)).toContain("error=OAuthCancelado");
    expect(llamarApi).not.toHaveBeenCalled();
  });

  it("con state válido intercambia el código y no devuelve ningún token", async () => {
    almacen.set(COOKIE_STATE, "el-state");
    llamarApi.mockResolvedValue(SESION);

    const respuesta = await getCallback(
      callback({ state: "el-state", code: "simulado:ana@empresa.com" }),
    );

    expect(ubicacion(respuesta)).toContain("/onboarding/empresa");
    expect(llamarApi).toHaveBeenCalledWith("/auth/google/callback", {
      method: "POST",
      body: { codigo: "simulado:ana@empresa.com" },
    });
    // The state cookie is single use: it is deleted whatever the outcome.
    expect(cookiesBorradas).toContain(COOKIE_STATE);
  });

  it("una empresa con el onboarding hecho entra al panel", async () => {
    almacen.set(COOKIE_STATE, "el-state");
    llamarApi.mockResolvedValue({ ...SESION, onboarding_completo: true });

    const respuesta = await getCallback(
      callback({ state: "el-state", code: "simulado:ana@empresa.com" }),
    );

    expect(ubicacion(respuesta)).toContain("/panel");
  });
});

describe("POST /api/auth/refresh", () => {
  it("sin cookie de refresh contesta 401 y no llama al backend", async () => {
    const respuesta = await postRefresh();

    expect(respuesta.status).toBe(401);
    expect(llamarApi).not.toHaveBeenCalled();
  });

  it("rota la sesión leyendo el token de la cookie, nunca del cuerpo", async () => {
    almacen.set("cheatsheet_refresh", "el-refresh-viejo");
    llamarApi.mockResolvedValue(SESION);

    const respuesta = await postRefresh();

    expect(respuesta.status).toBe(200);
    expect(llamarApi).toHaveBeenCalledWith("/auth/refresh", {
      method: "POST",
      body: { refresh_token: "el-refresh-viejo" },
    });
    expect(JSON.stringify(await respuesta.json())).not.toContain("un-refresh-token");
  });

  it("un refresh rechazado limpia las dos cookies", async () => {
    almacen.set("cheatsheet_refresh", "un-refresh-robado");
    llamarApi.mockRejectedValue(new ErrorDeApi(409, "reuso", "ReusoDeRefreshDetectado"));

    const respuesta = await postRefresh();

    expect(respuesta.status).toBe(401);
    // Otherwise the browser loops through here on every request with a dead token.
    expect(cookiesBorradas).toContain("cheatsheet_session");
    expect(cookiesBorradas).toContain("cheatsheet_refresh");
  });
});

describe("POST /api/auth/invitaciones/aceptar", () => {
  it("deja la sesión en cookies y no devuelve tokens", async () => {
    llamarApi.mockResolvedValue(SESION);

    const respuesta = await postAceptar(
      new Request("http://test/api/auth/invitaciones/aceptar", {
        method: "POST",
        body: JSON.stringify({ token: "un-token", nombre: "Beto", contrasena: "12345678" }),
      }),
    );

    const cuerpo = JSON.stringify(await respuesta.json());
    expect(cuerpo).toBe(JSON.stringify({ onboarding_completo: false }));
    expect(cuerpo).not.toContain("un-access-token");
    expect(cookiesPuestas.map((puesta) => puesta.name)).toContain("cheatsheet_session");
  });

  it("una invitación inválida llega con su código y sin sesión", async () => {
    llamarApi.mockRejectedValue(new ErrorDeApi(409, "invalida", "InvitacionInvalida"));

    const respuesta = await postAceptar(
      new Request("http://test/api/auth/invitaciones/aceptar", {
        method: "POST",
        body: JSON.stringify({ token: "vencido", nombre: "Beto", contrasena: "12345678" }),
      }),
    );

    expect(respuesta.status).toBe(409);
    expect(await respuesta.json()).toEqual({ error: "InvitacionInvalida" });
    expect(cookiesPuestas).toHaveLength(0);
  });
});
