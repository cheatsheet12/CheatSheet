/**
 * The BFF boundary for user administration (caso 44).
 *
 * Same property as the auth handlers: whatever the backend returns, no token leaves
 * here. And one more that only these routes have — every one of them refuses without a
 * session, before the backend is called at all.
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
const { GET: getUsuarios } = await import("@/app/api/usuarios/route");
const { POST: postInvitacion } = await import("@/app/api/usuarios/invitaciones/route");
const { POST: postReenvio } = await import(
  "@/app/api/usuarios/invitaciones/[invitacionId]/reenvio/route"
);
const { DELETE: deleteInvitacion } = await import(
  "@/app/api/usuarios/invitaciones/[invitacionId]/route"
);
const { PATCH: patchRol } = await import("@/app/api/usuarios/[usuarioId]/rol/route");
const { POST: postDesactivacion } = await import(
  "@/app/api/usuarios/[usuarioId]/desactivacion/route"
);
const { POST: postReactivacion } = await import(
  "@/app/api/usuarios/[usuarioId]/reactivacion/route"
);
const { GET: getPreferencias, PUT: putPreferencias } = await import(
  "@/app/api/usuarios/preferencias/route"
);

const USUARIO = {
  id: "3f1c2b8e-0000-4000-8000-000000000002",
  email: "beto@empresa.com",
  nombre: "Beto Gomez",
  rol: "OPERADOR",
  estado: "INVITADO",
  invitacion_id: "3f1c2b8e-0000-4000-8000-000000000003",
};

function pedido(cuerpo: unknown = {}): Request {
  return new Request("http://test/api/usuarios", {
    method: "POST",
    body: JSON.stringify(cuerpo),
  });
}

afterEach(() => {
  cookieDeSesion = undefined;
  llamarApi.mockReset();
});

describe("sin sesión", () => {
  it("ninguna ruta llega al backend", async () => {
    const respuestas = await Promise.all([
      getUsuarios(),
      postInvitacion(pedido({ email: "beto@empresa.com", rol: "OPERADOR" })),
      postReenvio(pedido(), { params: { invitacionId: "una-invitacion" } }),
      deleteInvitacion(pedido(), { params: { invitacionId: "una-invitacion" } }),
      patchRol(pedido({ rol: "OPERADOR" }), { params: { usuarioId: "un-usuario" } }),
      postDesactivacion(pedido(), { params: { usuarioId: "un-usuario" } }),
      postReactivacion(pedido(), { params: { usuarioId: "un-usuario" } }),
      getPreferencias(),
      putPreferencias(pedido({ pref_idioma: "es-AR" })),
    ]);

    expect(respuestas.map((respuesta) => respuesta.status)).toEqual(Array(9).fill(401));
    expect(llamarApi).not.toHaveBeenCalled();
  });
});

describe("con sesión", () => {
  it("lista los usuarios de la empresa", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue([USUARIO]);

    const respuesta = await getUsuarios();

    expect(respuesta.status).toBe(200);
    expect(await respuesta.json()).toEqual([USUARIO]);
    expect(llamarApi).toHaveBeenCalledWith("/usuarios", { method: "GET" });
  });

  it("el reenvío no devuelve ningún token al navegador", async () => {
    cookieDeSesion = "un-access-token";
    // If the backend ever leaked the new invitation token, this is where it would show.
    llamarApi.mockResolvedValue({ ok: true });

    const respuesta = await postReenvio(pedido(), {
      params: { invitacionId: "una-invitacion" },
    });

    const cuerpo = JSON.stringify(await respuesta.json());
    expect(cuerpo).not.toContain("token");
    expect(llamarApi).toHaveBeenCalledWith("/usuarios/invitaciones/una-invitacion/reenvio", {
      method: "POST",
      body: {},
    });
  });

  it("reactivar no manda cuerpo, porque el rol anterior nunca se borró", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ ...USUARIO, estado: "ACTIVO" });

    await postReactivacion(pedido(), { params: { usuarioId: "u-1" } });

    expect(llamarApi).toHaveBeenCalledWith("/usuarios/u-1/reactivacion", {
      method: "POST",
      body: {},
    });
  });

  it("un 403 del backend llega como 403 y con su código", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockRejectedValue(new ErrorDeApi(403, "Solo un Administrador", "PermisoDenegado"));

    const respuesta = await postInvitacion(pedido({ email: "beto@empresa.com" }));

    expect(respuesta.status).toBe(403);
    expect(await respuesta.json()).toEqual({ error: "PermisoDenegado" });
  });

  it("las preferencias se guardan tal como llegaron del formulario", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({
      pref_idioma: "es-AR",
      pref_zona_horaria: "America/Argentina/Cordoba",
      pref_suscripciones: {},
    });

    await putPreferencias(pedido({ pref_zona_horaria: "America/Argentina/Cordoba" }));

    expect(llamarApi).toHaveBeenCalledWith("/usuarios/yo/preferencias", {
      method: "PUT",
      body: { pref_zona_horaria: "America/Argentina/Cordoba" },
    });
  });
});
