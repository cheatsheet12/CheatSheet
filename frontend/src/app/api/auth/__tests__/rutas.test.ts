/**
 * The BFF boundary for authentication.
 *
 * The property under test is what the browser is **not** told. The backend answers with
 * an access token and a refresh token; the response that leaves this handler must carry
 * neither. That is the whole reason the BFF exists, and it is one careless
 * `NextResponse.json(sesion)` away from being false.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

const cookiesPuestas: Array<Record<string, unknown>> = [];
const cookiesBorradas: string[] = [];
let cookieDeSesion: string | undefined;

vi.mock("next/headers", () => ({
  cookies: () => ({
    get: (nombre: string) =>
      nombre === "cheatsheet_session" && cookieDeSesion !== undefined
        ? { name: nombre, value: cookieDeSesion }
        : undefined,
    set: (opciones: Record<string, unknown>) => cookiesPuestas.push(opciones),
    delete: (nombre: string) => cookiesBorradas.push(nombre),
  }),
}));

const llamarApi = vi.fn();
vi.mock("@/lib/api", async () => {
  const real = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...real, llamarApi: (...args: unknown[]) => llamarApi(...args) };
});

const { ErrorDeApi } = await import("@/lib/api");
const { POST: postRegistro } = await import("@/app/api/auth/registro/route");
const { POST: postLogin } = await import("@/app/api/auth/login/route");
const { POST: postLogout } = await import("@/app/api/auth/logout/route");
const { GET: getEmpresa, PUT: putEmpresa } = await import("@/app/api/auth/empresa/route");
const { POST: postPadron } = await import("@/app/api/auth/empresa/padron/route");

const SESION = {
  access_token: "un-access-token",
  refresh_token: "un-refresh-token",
  empresa_id: "3f1c2b8e-0000-4000-8000-000000000001",
  usuario_id: "3f1c2b8e-0000-4000-8000-000000000002",
  onboarding_completo: false,
};

function pedido(cuerpo: unknown): Request {
  return new Request("http://test/api/auth", {
    method: "POST",
    body: JSON.stringify(cuerpo),
  });
}

afterEach(() => {
  cookiesPuestas.length = 0;
  cookiesBorradas.length = 0;
  cookieDeSesion = undefined;
  llamarApi.mockReset();
});

describe("POST /api/auth/registro", () => {
  it("no devuelve ningún token al navegador", async () => {
    llamarApi.mockResolvedValue(SESION);

    const respuesta = await postRegistro(pedido({ email: "ana@empresa.com" }));
    const cuerpo = JSON.stringify(await respuesta.json());

    expect(cuerpo).not.toContain("un-access-token");
    expect(cuerpo).not.toContain("un-refresh-token");
    expect(cuerpo).toBe(JSON.stringify({ onboarding_completo: false }));
  });

  it("guarda los dos tokens en cookies HttpOnly", async () => {
    llamarApi.mockResolvedValue(SESION);

    await postRegistro(pedido({}));

    expect(cookiesPuestas).toHaveLength(2);
    expect(cookiesPuestas.every((cookie) => cookie.httpOnly === true)).toBe(true);
  });

  it("el refresh queda acotado a /api/auth y SameSite=strict", async () => {
    llamarApi.mockResolvedValue(SESION);

    await postRegistro(pedido({}));

    const refresh = cookiesPuestas.find((cookie) => cookie.name === "cheatsheet_refresh");
    expect(refresh?.path).toBe("/api/auth");
    expect(refresh?.sameSite).toBe("strict");
  });

  it("propaga el código del error y no el mensaje interno", async () => {
    llamarApi.mockRejectedValue(
      new ErrorDeApi(409, "Ya existe una cuenta con el email ana@empresa.com", "EmailYaRegistrado"),
    );

    const respuesta = await postRegistro(pedido({}));

    expect(respuesta.status).toBe(409);
    expect(await respuesta.json()).toEqual({ error: "EmailYaRegistrado" });
  });

  it("un fallo inesperado no filtra nada", async () => {
    llamarApi.mockRejectedValue(new Error("connect ECONNREFUSED 10.0.0.5:8000"));

    const respuesta = await postRegistro(pedido({}));
    const cuerpo = JSON.stringify(await respuesta.json());

    expect(respuesta.status).toBe(500);
    expect(cuerpo).not.toContain("10.0.0.5");
  });
});

describe("POST /api/auth/login", () => {
  it("tampoco devuelve tokens", async () => {
    llamarApi.mockResolvedValue({ ...SESION, onboarding_completo: true });

    const respuesta = await postLogin(pedido({}));

    expect(await respuesta.json()).toEqual({ onboarding_completo: true });
    expect(cookiesPuestas).toHaveLength(2);
  });

  it("credenciales inválidas viajan como código, no como texto del backend", async () => {
    llamarApi.mockRejectedValue(
      new ErrorDeApi(409, "Email o contrasena incorrectos", "CredencialesInvalidas"),
    );

    expect(await (await postLogin(pedido({}))).json()).toEqual({
      error: "CredencialesInvalidas",
    });
  });
});

describe("POST /api/auth/logout", () => {
  it("borra las dos cookies", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({});

    await postLogout();

    expect(cookiesBorradas).toContain("cheatsheet_session");
    expect(cookiesBorradas).toContain("cheatsheet_refresh");
  });

  it("cierra la sesión aunque el backend falle", async () => {
    llamarApi.mockRejectedValue(new Error("la API se cayo"));

    const respuesta = await postLogout();

    expect(respuesta.status).toBe(200);
    expect(cookiesBorradas).toContain("cheatsheet_session");
  });
});

describe("PUT /api/auth/empresa", () => {
  it("sin sesión responde 401 y no llama al backend", async () => {
    const respuesta = await putEmpresa(pedido({}));

    expect(respuesta.status).toBe(401);
    expect(llamarApi).not.toHaveBeenCalled();
  });

  it("con sesión reenvía y devuelve el estado del onboarding", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ onboarding_completo: true });

    const respuesta = await putEmpresa(pedido({ cuit: "30712345671" }));

    expect(await respuesta.json()).toEqual({ onboarding_completo: true });
  });

  it("un error de validación sí lleva el detalle, que es para el usuario", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockRejectedValue(
      new ErrorDeApi(422, "El digito verificador del CUIT no es correcto", "EntradaInvalida"),
    );

    const respuesta = await putEmpresa(pedido({}));

    expect(await respuesta.json()).toEqual({
      error: "EntradaInvalida",
      detalle: "El digito verificador del CUIT no es correcto",
    });
  });
});

describe("GET /api/auth/empresa", () => {
  it("sin sesión no pregunta nada al backend", async () => {
    const respuesta = await getEmpresa();

    expect(respuesta.status).toBe(401);
    expect(llamarApi).not.toHaveBeenCalled();
  });

  it("reenvía los datos fiscales que la pantalla de edición carga en el formulario", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({
      razon_social: "Panaderia Dona Rosa",
      onboarding_completo: true,
      cuit: "30712345671",
      condicion_iva: "MONOTRIBUTO",
      nombre_responsable: "Rosa Diaz",
      email_contacto: "rosa@panaderia.com",
    });

    const cuerpo = await (await getEmpresa()).json();

    expect(cuerpo.cuit).toBe("30712345671");
    expect(cuerpo.condicion_iva).toBe("MONOTRIBUTO");
  });
});

describe("POST /api/auth/empresa/padron", () => {
  it("sin sesión no consulta el padrón", async () => {
    const respuesta = await postPadron(pedido({ cuit: "30712345671" }));

    expect(respuesta.status).toBe(401);
    expect(llamarApi).not.toHaveBeenCalled();
  });

  it("los tres estados llegan al navegador tal como vinieron", async () => {
    // Aplanar «no encontrado» y «no disponible» en un booleano acá desharía la distinción
    // sobre la que se apoya toda la unidad: uno bloquea al Administrador y el otro no.
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({
      estado: "NO_DISPONIBLE",
      datos: null,
      motivo: "La empresa no tiene conectada la integracion con ARCA",
    });

    const cuerpo = await (await postPadron(pedido({ cuit: "30712345671" }))).json();

    expect(cuerpo.estado).toBe("NO_DISPONIBLE");
    expect(cuerpo.motivo).toContain("no tiene conectada");
  });

  it("el CUIT viaja en el cuerpo, nunca en la URL", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ estado: "NO_ENCONTRADO", datos: null, motivo: null });

    await postPadron(pedido({ cuit: "30712345671" }));

    const [ruta, opciones] = llamarApi.mock.calls[0] as [string, { body: unknown }];
    expect(ruta).toBe("/auth/empresa/padron");
    expect(ruta).not.toContain("30712345671");
    expect(opciones.body).toEqual({ cuit: "30712345671" });
  });
});
