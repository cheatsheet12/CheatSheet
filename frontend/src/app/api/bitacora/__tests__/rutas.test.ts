/**
 * La frontera del BFF del panel de auditoría (épico 10).
 *
 * Las propiedades de siempre —ninguna ruta llega al backend sin sesión, y el query string se
 * reenvía entero— más las dos que son de esta unidad:
 *
 * - **La bitácora sólo tiene `GET`.** HU-E12-01 RN-04 la hace de sólo consulta, y este archivo
 *   afirma que el módulo no exporta ningún otro verbo: si alguien agregara un `DELETE`, esto
 *   se cae antes de que llegue a una revisión.
 * - **El acuse de lectura no lleva id de usuario.** El destinatario sale de la sesión del lado
 *   del backend, y ninguna ruta de acá puede pedir la bandeja de otra persona.
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

const rutaBitacora = await import("@/app/api/bitacora/route");
const rutaOperacion = await import("@/app/api/bitacora/[operacionId]/route");
const rutaNotificaciones = await import("@/app/api/notificaciones/route");
const rutaLectura = await import("@/app/api/notificaciones/[notificacionId]/lectura/route");
const rutaSoporte = await import("@/app/api/soporte/route");

function lectura(consulta = ""): Request {
  return new Request(`http://test/api/bitacora${consulta}`, { method: "GET" });
}

function pedido(cuerpo: unknown = {}): Request {
  return new Request("http://test/api/soporte", {
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
      rutaBitacora.GET(lectura()),
      rutaOperacion.GET(lectura(), { params: { operacionId: "op1" } }),
      rutaNotificaciones.GET(lectura()),
      rutaLectura.POST(lectura(), { params: { notificacionId: "n1" } }),
      rutaSoporte.GET(lectura()),
      rutaSoporte.POST(pedido({ asunto: "x", descripcion: "y" })),
    ]);

    expect(respuestas.map((respuesta) => respuesta.status)).toEqual(Array(6).fill(401));
    expect(llamarApi).not.toHaveBeenCalled();
  });
});

describe("la bitácora", () => {
  it("es de sólo consulta", () => {
    // RN-04, hecho forma del módulo: no hay otro verbo que exportar.
    expect(Object.keys(rutaBitacora).sort()).toEqual(["GET", "dynamic"]);
    expect(Object.keys(rutaOperacion).sort()).toEqual(["GET", "dynamic"]);
  });

  it("reenvía el query string entero, sin conocer los filtros", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ operaciones: [], total: 0 });

    await rutaBitacora.GET(lectura("?modulo=billing&iniciador=ia&pagina=2"));

    expect(llamarApi).toHaveBeenCalledWith("/bitacora?modulo=billing&iniciador=ia&pagina=2", {
      method: "GET",
    });
  });

  it("el detalle usa el id de la ruta", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ operacion: {}, timeline: [] });

    await rutaOperacion.GET(lectura(), { params: { operacionId: "op-1" } });

    expect(llamarApi).toHaveBeenCalledWith("/bitacora/op-1", { method: "GET" });
  });

  it("un rol sin acceso recibe el motivo del backend", async () => {
    cookieDeSesion = "un-access-token";
    const { ErrorDeApi } = await import("@/lib/api");
    llamarApi.mockRejectedValue(
      new ErrorDeApi(422, "El rol Solo Lectura no accede a la bitácora de operaciones"),
    );

    const respuesta = await rutaBitacora.GET(lectura());
    const cuerpo = (await respuesta.json()) as { detalle?: string };

    expect(respuesta.status).toBe(422);
    expect(cuerpo.detalle).toContain("Solo Lectura");
  });
});

describe("las notificaciones", () => {
  it("no llevan id de usuario en ninguna ruta", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ notificaciones: [], no_leidas: 0 });

    await rutaNotificaciones.GET(lectura("?solo_no_leidas=true"));

    expect(llamarApi).toHaveBeenCalledWith("/notificaciones?solo_no_leidas=true", {
      method: "GET",
    });
  });

  it("el acuse de lectura es un POST con cuerpo vacío", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ id: "n1", leida: true });

    await rutaLectura.POST(lectura(), { params: { notificacionId: "n1" } });

    expect(llamarApi).toHaveBeenCalledWith("/notificaciones/n1/lectura", {
      method: "POST",
      body: {},
    });
  });
});

describe("el soporte", () => {
  it("manda el cuerpo tal cual", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ id: "s1" });

    await rutaSoporte.POST(
      pedido({ asunto: "No puedo emitir", descripcion: "ARCA falla", prioridad: "ALTA" }),
    );

    expect(llamarApi).toHaveBeenCalledWith("/soporte", {
      method: "POST",
      body: { asunto: "No puedo emitir", descripcion: "ARCA falla", prioridad: "ALTA" },
    });
  });

  it("no ofrece borrar una solicitud", () => {
    // Un pedido de ayuda borrado es un pedido que nadie puede demostrar que hizo.
    expect(Object.keys(rutaSoporte).sort()).toEqual(["GET", "POST", "dynamic"]);
  });
});
