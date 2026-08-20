/**
 * The BFF boundary for the integrations screen (case 21).
 *
 * Same two properties as the user-administration handlers: every route refuses without a
 * session before the backend is called at all, and whatever the backend returns, no token
 * leaves here.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

let cookieDeSesion: string | undefined;

vi.mock("next/headers", () => ({
  cookies: () => ({
    get: (nombre: string) =>
      nombre === "cheatsheet_session" && cookieDeSesion !== undefined
        ? { name: nombre, value: cookieDeSesion }
        : undefined,
    set: () => undefined,
    delete: () => undefined,
  }),
}));

const llamarApi = vi.fn();
vi.mock("@/lib/api", async () => {
  const real = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...real, llamarApi: (...args: unknown[]) => llamarApi(...args) };
});

const { ErrorDeApi } = await import("@/lib/api");
const { GET: getIntegraciones } = await import("@/app/api/integraciones/route");
const { POST: postVerificacion } = await import("@/app/api/integraciones/verificacion/route");
const { PUT: putConexion } = await import("@/app/api/integraciones/[sistema]/conexion/route");
const { POST: postAutorizacion } = await import(
  "@/app/api/integraciones/[sistema]/autorizacion/route"
);
const { POST: postCanje } = await import(
  "@/app/api/integraciones/[sistema]/autorizacion/canje/route"
);

const LISTADO = { integraciones: [], verificado_en: null };

function pedido(cuerpo: unknown): Request {
  return new Request("http://test/api/integraciones/ARCA/conexion", {
    method: "PUT",
    body: JSON.stringify(cuerpo),
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  cookieDeSesion = undefined;
  vi.clearAllMocks();
});

describe("BFF de integraciones", () => {
  it("sin sesion, ninguna ruta llama al backend", async () => {
    const respuestas = await Promise.all([
      getIntegraciones(),
      postVerificacion(),
      putConexion(pedido({ contenido: "eA==" }), { params: { sistema: "ARCA" } }),
      postAutorizacion(pedido({}), { params: { sistema: "MERCADOPAGO" } }),
      postCanje(pedido({ codigo: "c", estado: "e" }), { params: { sistema: "MERCADOPAGO" } }),
    ]);

    for (const respuesta of respuestas) {
      expect(respuesta.status).toBe(401);
    }
    expect(llamarApi).not.toHaveBeenCalled();
  });

  it("con sesion, el listado se reenvia al backend", async () => {
    cookieDeSesion = "un-token";
    llamarApi.mockResolvedValue(LISTADO);

    const respuesta = await getIntegraciones();

    expect(respuesta.status).toBe(200);
    expect(llamarApi).toHaveBeenCalledWith("/integraciones", { method: "GET" });
  });

  it("la verificacion viaja como POST", async () => {
    cookieDeSesion = "un-token";
    llamarApi.mockResolvedValue(LISTADO);

    await postVerificacion();

    expect(llamarApi).toHaveBeenCalledWith("/integraciones/verificacion", { method: "POST" });
  });

  it("la conexion viaja como PUT con el cuerpo y el sistema en la ruta", async () => {
    cookieDeSesion = "un-token";
    llamarApi.mockResolvedValue({});

    await putConexion(pedido({ contenido: "eA==", parametros: {} }), {
      params: { sistema: "MERCADOPAGO" },
    });

    expect(llamarApi).toHaveBeenCalledWith("/integraciones/MERCADOPAGO/conexion", {
      method: "PUT",
      body: { contenido: "eA==", parametros: {} },
    });
  });

  it("la autorizacion viaja como POST y sin cuerpo", async () => {
    cookieDeSesion = "un-token";
    llamarApi.mockResolvedValue({ url: "https://proveedor.test", expira_en_segundos: 600 });

    await postAutorizacion(pedido({}), { params: { sistema: "MERCADOPAGO" } });

    expect(llamarApi).toHaveBeenCalledWith("/integraciones/MERCADOPAGO/autorizacion", {
      method: "POST",
    });
  });

  it("el canje lleva el codigo y el estado en el cuerpo, no en la URL", async () => {
    // Así no quedan en el historial del navegador ni en ningún log intermedio.
    cookieDeSesion = "un-token";
    llamarApi.mockResolvedValue({});

    await postCanje(pedido({ codigo: "el-codigo", estado: "el-estado" }), {
      params: { sistema: "MERCADOPAGO" },
    });

    expect(llamarApi).toHaveBeenCalledWith("/integraciones/MERCADOPAGO/autorizacion/canje", {
      method: "POST",
      body: { codigo: "el-codigo", estado: "el-estado" },
    });
  });

  it("un error del backend llega con su codigo y sin filtrar el token", async () => {
    cookieDeSesion = "un-token-secreto";
    llamarApi.mockRejectedValue(new ErrorDeApi(403, "Solo un Administrador", "PermisoDenegado"));

    const respuesta = await putConexion(pedido({ contenido: "eA==" }), {
      params: { sistema: "ARCA" },
    });

    expect(respuesta.status).toBe(403);
    expect(await respuesta.text()).not.toContain("un-token-secreto");
  });
});
