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
/** Expiries sent with `set({ maxAge: 0 })`: what actually removes a cookie scoped to a path. */
const expiraciones: Array<Record<string, unknown>> = [];
const almacen = new Map<string, string>();

vi.mock("next/headers", () => ({
  cookies: () => ({
    get: (nombre: string) =>
      almacen.has(nombre) ? { name: nombre, value: almacen.get(nombre) } : undefined,
    set: (opciones: Record<string, unknown>) => {
      if (opciones.maxAge === 0) {
        // A browser drops the cookie only when name, path and domain match the one it holds.
        expiraciones.push(opciones);
        cookiesBorradas.push(String(opciones.name));
        almacen.delete(String(opciones.name));
        return;
      }
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
const {
  GET: getGoogle,
  POST: postGoogle,
  COOKIE_STATE,
  COOKIE_CONSENTIMIENTO,
} = await import("@/app/api/auth/google/route");
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

function inicio(parametros: Record<string, string> = {}): Request {
  const url = new URL("http://test/api/auth/google");
  for (const [clave, valor] of Object.entries(parametros)) {
    url.searchParams.set(clave, valor);
  }
  return new Request(url);
}

function formulario(
  campos: Record<string, string>,
  cabeceras: Record<string, string> = {},
): Request {
  return new Request("http://test/api/auth/google", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded", ...cabeceras },
    body: new URLSearchParams(campos).toString(),
  });
}

/** What the browser needs to see to drop an OAuth cookie it was given with `path=/api/auth`. */
function expiracionDe(nombre: string): Record<string, unknown> | undefined {
  return expiraciones.find((expiracion) => expiracion.name === nombre);
}

const EXPIRA_CON_LOS_ATRIBUTOS_CON_QUE_SE_PUSO = expect.objectContaining({
  value: "",
  path: "/api/auth",
  maxAge: 0,
  httpOnly: true,
  sameSite: "lax",
});

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
  expiraciones.length = 0;
  almacen.clear();
  llamarApi.mockReset();
});

describe("GET /api/auth/google", () => {
  it("guarda el state y redirige a donde diga el backend", async () => {
    llamarApi.mockResolvedValue({ url: "https://accounts.google.com/o/oauth2/v2/auth?x=1" });

    const respuesta = await getGoogle(inicio());

    expect(respuesta.status).toBe(307);
    expect(ubicacion(respuesta)).toContain("accounts.google.com");
    const cookie = cookiesPuestas.find((puesta) => puesta.name === COOKIE_STATE);
    expect(cookie?.httpOnly).toBe(true);
    // `lax`, not `strict`: the browser returns here from Google's domain.
    expect(cookie?.sameSite).toBe("lax");
  });

  it("una URL con versiones NO deja consentimiento: la aceptación no viaja por GET", async () => {
    llamarApi.mockResolvedValue({ url: "https://accounts.google.com/o/oauth2/v2/auth?x=1" });

    await getGoogle(inicio({ terminos: "1.1", privacidad: "1.0" }));

    expect(cookiesPuestas.some((puesta) => puesta.name === COOKIE_CONSENTIMIENTO)).toBe(false);
  });

  it("sin consentimiento borra uno viejo con el path con que se puso (si no, el navegador lo conserva)", async () => {
    llamarApi.mockResolvedValue({ url: "https://accounts.google.com/o/oauth2/v2/auth?x=1" });
    almacen.set(COOKIE_CONSENTIMIENTO, '{"version_terminos":"0.1","version_privacidad":"0.1"}');

    await getGoogle(inicio());

    expect(cookiesPuestas.some((puesta) => puesta.name === COOKIE_CONSENTIMIENTO)).toBe(false);
    expect(expiracionDe(COOKIE_CONSENTIMIENTO)).toEqual(EXPIRA_CON_LOS_ATRIBUTOS_CON_QUE_SE_PUSO);
    expect(almacen.has(COOKIE_CONSENTIMIENTO)).toBe(false);
  });

  it("si el backend no tiene Google configurado, vuelve al inicio con el motivo", async () => {
    llamarApi.mockRejectedValue(new ErrorDeApi(409, "no configurado", "OAuthFallido"));

    const respuesta = await getGoogle(inicio());

    expect(ubicacion(respuesta)).toContain("error=OAuthFallido");
  });
});

describe("POST /api/auth/google", () => {
  const GOOGLE = "https://accounts.google.com/o/oauth2/v2/auth?x=1";

  it("guarda el consentimiento en una cookie HttpOnly de 10 minutos y redirige con 303 (caso 20)", async () => {
    llamarApi.mockResolvedValue({ url: GOOGLE });

    const respuesta = await postGoogle(formulario({ terminos: "1.1", privacidad: "1.0" }));

    // 303, not 307: the browser must follow with a GET, not repeat the POST at Google.
    expect(respuesta.status).toBe(303);
    expect(ubicacion(respuesta)).toContain("accounts.google.com");
    const cookie = cookiesPuestas.find((puesta) => puesta.name === COOKIE_CONSENTIMIENTO);
    expect(cookie?.httpOnly).toBe(true);
    expect(cookie?.sameSite).toBe("lax");
    expect(cookie?.path).toBe("/api/auth");
    expect(cookie?.maxAge).toBe(600);
    expect(JSON.parse(String(cookie?.value))).toEqual({
      version_terminos: "1.1",
      version_privacidad: "1.0",
    });
    expect(cookiesPuestas.some((puesta) => puesta.name === COOKIE_STATE)).toBe(true);
  });

  it.each([
    ["con formato inválido", { terminos: "uno", privacidad: "1.0" }],
    ["demasiado larga", { terminos: "1.".padEnd(40, "0"), privacidad: "1.0" }],
    ["incompleta", { terminos: "1.1" }],
    ["vacía", { terminos: "", privacidad: "" }],
  ])("una versión %s no se guarda y borra la anterior", async (_motivo, campos) => {
    llamarApi.mockResolvedValue({ url: GOOGLE });
    almacen.set(COOKIE_CONSENTIMIENTO, '{"version_terminos":"0.1","version_privacidad":"0.1"}');

    await postGoogle(formulario(campos));

    expect(cookiesPuestas.some((puesta) => puesta.name === COOKIE_CONSENTIMIENTO)).toBe(false);
    expect(expiracionDe(COOKIE_CONSENTIMIENTO)).toEqual(EXPIRA_CON_LOS_ATRIBUTOS_CON_QUE_SE_PUSO);
  });

  it("un formulario enviado desde otro origen no registra consentimiento", async () => {
    llamarApi.mockResolvedValue({ url: GOOGLE });

    const respuesta = await postGoogle(
      formulario(
        { terminos: "1.1", privacidad: "1.0" },
        { origin: "https://sitio-malicioso.example" },
      ),
    );

    expect(cookiesPuestas.some((puesta) => puesta.name === COOKIE_CONSENTIMIENTO)).toBe(false);
    // The sign-in itself is harmless: only the consent is withheld.
    expect(ubicacion(respuesta)).toContain("accounts.google.com");
  });

  it("un formulario del propio sitio (Origin igual al de la app) sí lo registra", async () => {
    llamarApi.mockResolvedValue({ url: GOOGLE });

    await postGoogle(
      formulario({ terminos: "1.1", privacidad: "1.0" }, { origin: "http://localhost:3000" }),
    );

    expect(cookiesPuestas.some((puesta) => puesta.name === COOKIE_CONSENTIMIENTO)).toBe(true);
  });

  it("si el backend no tiene Google configurado, vuelve al inicio con el motivo", async () => {
    llamarApi.mockRejectedValue(new ErrorDeApi(409, "no configurado", "OAuthFallido"));

    const respuesta = await postGoogle(formulario({ terminos: "1.1", privacidad: "1.0" }));

    expect(respuesta.status).toBe(303);
    expect(ubicacion(respuesta)).toContain("error=OAuthFallido");
    expect(cookiesPuestas.some((puesta) => puesta.name === COOKIE_CONSENTIMIENTO)).toBe(false);
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
    // The state cookie is single use: it is deleted whatever the outcome, with the path it was
    // set with. A plain `delete(name)` expires `Path=/` and the browser keeps the real one for
    // the rest of its 10 minutes, so a used state could be replayed.
    expect(expiracionDe(COOKIE_STATE)).toEqual(EXPIRA_CON_LOS_ATRIBUTOS_CON_QUE_SE_PUSO);
  });

  it("reenvía el consentimiento guardado al backend y lo borra después (caso 20)", async () => {
    almacen.set(COOKIE_STATE, "el-state");
    almacen.set(COOKIE_CONSENTIMIENTO, '{"version_terminos":"1.1","version_privacidad":"1.0"}');
    llamarApi.mockResolvedValue(SESION);

    await getCallback(callback({ state: "el-state", code: "simulado:ana@empresa.com" }));

    expect(llamarApi).toHaveBeenCalledWith("/auth/google/callback", {
      method: "POST",
      body: {
        codigo: "simulado:ana@empresa.com",
        consentimiento: { version_terminos: "1.1", version_privacidad: "1.0" },
      },
    });
    expect(expiracionDe(COOKIE_CONSENTIMIENTO)).toEqual(EXPIRA_CON_LOS_ATRIBUTOS_CON_QUE_SE_PUSO);
    expect(almacen.has(COOKIE_CONSENTIMIENTO)).toBe(false);
  });

  it("una cookie de consentimiento ilegible se ignora y no rompe el ingreso", async () => {
    almacen.set(COOKIE_STATE, "el-state");
    almacen.set(COOKIE_CONSENTIMIENTO, "{no es json");
    llamarApi.mockResolvedValue(SESION);

    const respuesta = await getCallback(
      callback({ state: "el-state", code: "simulado:ana@empresa.com" }),
    );

    expect(ubicacion(respuesta)).toContain("/onboarding/empresa");
    expect(llamarApi).toHaveBeenCalledWith("/auth/google/callback", {
      method: "POST",
      body: { codigo: "simulado:ana@empresa.com" },
    });
  });

  it("el state inválido también borra el consentimiento", async () => {
    almacen.set(COOKIE_STATE, "el-state");
    almacen.set(COOKIE_CONSENTIMIENTO, '{"version_terminos":"1.1","version_privacidad":"1.0"}');

    await getCallback(callback({ state: "otro", code: "x" }));

    expect(expiracionDe(COOKIE_CONSENTIMIENTO)).toEqual(EXPIRA_CON_LOS_ATRIBUTOS_CON_QUE_SE_PUSO);
  });

  it.each(["ConsentimientoRequerido", "VersionLegalDesactualizada"])(
    "una cuenta nueva sin consentimiento válido (%s) vuelve al inicio con ese motivo",
    async (codigo) => {
      almacen.set(COOKIE_STATE, "el-state");
      llamarApi.mockRejectedValue(new ErrorDeApi(422, "falta", codigo));

      const respuesta = await getCallback(
        callback({ state: "el-state", code: "simulado:nueva@empresa.com" }),
      );

      expect(ubicacion(respuesta)).toContain(`error=${codigo}`);
    },
  );

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

  // A definitive "no" from the API ends the session. Not only 401: the backend answers 409 for
  // a revoked or reused token, and 422 when the cookie is not even a token.
  it.each([
    [401, "SesionInvalida"],
    [409, "SesionInvalida"],
    [422, "EntradaInvalida"],
  ])("un %i del backend cierra la sesión y borra las dos cookies", async (status, codigo) => {
    almacen.set("cheatsheet_session", "un-access-viejo");
    almacen.set("cheatsheet_refresh", "un-refresh-muerto");
    llamarApi.mockRejectedValue(new ErrorDeApi(status, "no", codigo));

    const respuesta = await postRefresh();

    expect(respuesta.status).toBe(401);
    expect(cookiesBorradas).toEqual(
      expect.arrayContaining(["cheatsheet_session", "cheatsheet_refresh"]),
    );
    expect(almacen.size).toBe(0);
  });

  // An API that cannot answer says nothing about the token, so the session stays as it was and
  // the next attempt renews normally.
  it.each([
    ["503", new ErrorDeApi(503, "caida", "ServicioNoDisponible")],
    ["500", new ErrorDeApi(500, "falla", "ErrorInterno")],
    ["un timeout de llamarApi (504)", new ErrorDeApi(504, "timeout", "TiempoAgotado")],
    ["una red caída (TypeError)", new TypeError("fetch failed")],
  ])("con %s conserva las dos cookies", async (_motivo, falla) => {
    almacen.set("cheatsheet_session", "un-access-viejo");
    almacen.set("cheatsheet_refresh", "un-refresh-vivo");
    llamarApi.mockRejectedValue(falla);

    const respuesta = await postRefresh();

    expect(cookiesBorradas).toHaveLength(0);
    expect(almacen.get("cheatsheet_session")).toBe("un-access-viejo");
    expect(almacen.get("cheatsheet_refresh")).toBe("un-refresh-vivo");
    expect(respuesta.status).toBe(502);
    expect(await respuesta.json()).toEqual({ error: "ServicioNoDisponible" });
  });

  it("tras una caída, el siguiente intento rota con el refresh que quedó", async () => {
    almacen.set("cheatsheet_refresh", "un-refresh-vivo");
    llamarApi.mockRejectedValueOnce(new ErrorDeApi(503, "caida", "ServicioNoDisponible"));
    llamarApi.mockResolvedValueOnce(SESION);

    const caida = await postRefresh();
    const recuperada = await postRefresh();

    expect(caida.status).toBe(502);
    expect(recuperada.status).toBe(200);
    expect(llamarApi).toHaveBeenLastCalledWith("/auth/refresh", {
      method: "POST",
      body: { refresh_token: "un-refresh-vivo" },
    });
    expect(almacen.get("cheatsheet_session")).toBe("un-access-token");
    expect(almacen.get("cheatsheet_refresh")).toBe("un-refresh-token");
    expect(cookiesBorradas).toHaveLength(0);
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
