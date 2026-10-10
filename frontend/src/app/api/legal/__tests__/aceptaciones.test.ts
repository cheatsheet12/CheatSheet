/**
 * The BFF boundary for accepting the legal documents in force (HU-E1-03 RN-03, HU-E1-08 RN-05).
 *
 * Two properties matter. It refuses without a session before the backend is called, and a
 * backend `403 AceptacionLegalPendiente` reaches the browser **with its status and its code**:
 * the browser-side watcher turns exactly that into the redirect to `/aceptacion-legal`, so a
 * handler that flattened it into a generic error would hide the block from the one thing that
 * can act on it.
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
const { POST } = await import("@/app/api/legal/aceptaciones/route");

const CUERPO = { documentos: [{ documento: "PRIVACIDAD", version: "1.0" }] };

function pedido(cuerpo: unknown = CUERPO): Request {
  return new Request("http://test/api/legal/aceptaciones", {
    method: "POST",
    body: JSON.stringify(cuerpo),
  });
}

afterEach(() => {
  cookieDeSesion = undefined;
  llamarApi.mockReset();
});

describe("POST /api/legal/aceptaciones", () => {
  it("sin sesión responde 401 y no llama al backend", async () => {
    const respuesta = await POST(pedido());

    expect(respuesta.status).toBe(401);
    expect(llamarApi).not.toHaveBeenCalled();
  });

  it("reenvía los documentos al backend tal como llegaron", async () => {
    cookieDeSesion = "token-de-sesion";
    llamarApi.mockResolvedValue(undefined);

    const respuesta = await POST(pedido());

    expect(respuesta.status).toBe(200);
    expect(llamarApi).toHaveBeenCalledWith("/legal/aceptaciones", {
      method: "POST",
      body: CUERPO,
    });
  });

  it("deja pasar un 409 de versión desactualizada con su código y su mensaje", async () => {
    cookieDeSesion = "token-de-sesion";
    llamarApi.mockRejectedValue(
      new ErrorDeApi(
        409,
        "La version 0.9 de PRIVACIDAD ya no es la vigente",
        "VersionLegalDesactualizada",
      ),
    );

    const respuesta = await POST(pedido());

    expect(respuesta.status).toBe(409);
    expect(await respuesta.json()).toMatchObject({ error: "VersionLegalDesactualizada" });
  });

  it("un 403 de rol no se confunde con el bloqueo por aceptación pendiente", async () => {
    cookieDeSesion = "token-de-sesion";
    llamarApi.mockRejectedValue(new ErrorDeApi(403, "Solo un Administrador", "PermisoDenegado"));

    const respuesta = await POST(pedido());

    expect(respuesta.status).toBe(403);
    expect(await respuesta.json()).toEqual({ error: "PermisoDenegado" });
  });

  it("un 403 AceptacionLegalPendiente llega al navegador con su estado y su código", async () => {
    cookieDeSesion = "token-de-sesion";
    llamarApi.mockRejectedValue(
      new ErrorDeApi(403, "Debe aceptar los documentos legales", "AceptacionLegalPendiente"),
    );

    const respuesta = await POST(pedido());

    expect(respuesta.status).toBe(403);
    expect(await respuesta.json()).toEqual({ error: "AceptacionLegalPendiente" });
  });
});
