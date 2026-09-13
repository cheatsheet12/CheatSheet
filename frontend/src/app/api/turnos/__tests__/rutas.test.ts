/**
 * La frontera del BFF para la agenda y los recursos reservables.
 *
 * Las mismas dos propiedades de siempre —ninguna ruta llega al backend sin sesión, y el query
 * string se reenvía entero— más las tres que son de esta unidad:
 *
 * - **No hay `DELETE` en turnos ni en recursos.** Un turno se cancela y un recurso se
 *   desactiva. El único `DELETE` del épico saca una excepción de disponibilidad, que es una
 *   anotación sobre un calendario y no una entidad del negocio.
 * - **Reprogramar no manda el estado.** La historia dice que reprogramar no es un estado, y
 *   este archivo es el último lugar donde alguien podría agregarlo sin querer.
 * - **Las tres configuraciones de un recurso son `PUT`**, porque reemplazan.
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
const rutaTurnos = await import("@/app/api/turnos/route");
const rutaTurno = await import("@/app/api/turnos/[turnoId]/route");
const rutaDisponibilidad = await import("@/app/api/turnos/disponibilidad/route");
const rutaCancelacion = await import("@/app/api/turnos/[turnoId]/cancelacion/route");
const rutaReprogramacion = await import("@/app/api/turnos/[turnoId]/reprogramacion/route");
const rutaAsistencia = await import("@/app/api/turnos/[turnoId]/asistencia/route");
const rutaRecursos = await import("@/app/api/recursos/route");
const rutaServicios = await import("@/app/api/recursos/servicios/route");
const rutaHorario = await import("@/app/api/recursos/[recursoId]/disponibilidad/route");
const rutaAsociados = await import("@/app/api/recursos/[recursoId]/servicios/route");
const rutaEstado = await import("@/app/api/recursos/[recursoId]/estado/route");
const rutaExcepciones = await import("@/app/api/recursos/[recursoId]/excepciones/route");
const rutaExcepcion = await import("@/app/api/recursos/[recursoId]/excepciones/[fecha]/route");

const TURNO = { id: "t1", estado: "RESERVADO" };

function pedido(cuerpo: unknown = {}, metodo = "POST"): Request {
  return new Request("http://test/api/turnos", { method: metodo, body: JSON.stringify(cuerpo) });
}

function lectura(consulta = ""): Request {
  return new Request(`http://test/api/turnos${consulta}`, { method: "GET" });
}

afterEach(() => {
  cookieDeSesion = undefined;
  llamarApi.mockReset();
});

describe("sin sesión", () => {
  it("ninguna ruta llega al backend", async () => {
    const respuestas = await Promise.all([
      rutaTurnos.GET(lectura()),
      rutaTurnos.POST(pedido({ cliente_id: "cl1" })),
      rutaTurno.GET(lectura(), { params: { turnoId: "t1" } }),
      rutaDisponibilidad.GET(lectura("?recurso_id=r1&fecha=2027-09-07")),
      rutaCancelacion.POST(lectura(), { params: { turnoId: "t1" } }),
      rutaReprogramacion.POST(pedido({ inicio: "x" }), { params: { turnoId: "t1" } }),
      rutaAsistencia.POST(pedido({ asistio: true }), { params: { turnoId: "t1" } }),
      rutaRecursos.GET(lectura()),
      rutaRecursos.POST(pedido({ nombre: "Sala" })),
      rutaServicios.GET(),
      rutaHorario.PUT(pedido({ patrones: [] }, "PUT"), { params: { recursoId: "r1" } }),
      rutaAsociados.PUT(pedido({ servicios: [] }, "PUT"), { params: { recursoId: "r1" } }),
      rutaEstado.PUT(pedido({ activo: false }, "PUT"), { params: { recursoId: "r1" } }),
      rutaExcepciones.POST(pedido({ fecha: "2027-12-25" }), { params: { recursoId: "r1" } }),
      rutaExcepcion.DELETE(lectura(), { params: { recursoId: "r1", fecha: "2027-12-25" } }),
    ]);

    expect(respuestas.map((respuesta) => respuesta.status)).toEqual(Array(15).fill(401));
    expect(llamarApi).not.toHaveBeenCalled();
  });
});

describe("la agenda", () => {
  it("reenvía el query string entero, sin conocer los filtros", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ turnos: [] });

    await rutaTurnos.GET(lectura("?recurso_id=r1&desde=2027-09-07&estado=CONFIRMADO"));

    expect(llamarApi).toHaveBeenCalledWith(
      "/turnos?recurso_id=r1&desde=2027-09-07&estado=CONFIRMADO",
      { method: "GET" },
    );
  });

  it("sin query string pide la agenda sin filtros: el backend decide el dia en curso", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ turnos: [] });

    await rutaTurnos.GET(lectura());

    expect(llamarApi).toHaveBeenCalledWith("/turnos", { method: "GET" });
  });

  it("el detalle usa el id de la ruta", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue(TURNO);

    await rutaTurno.GET(lectura(), { params: { turnoId: "t-1" } });

    expect(llamarApi).toHaveBeenCalledWith("/turnos/t-1", { method: "GET" });
  });

  it("la disponibilidad reenvía recurso y fecha", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ fecha: "2027-09-07", horarios: [] });

    await rutaDisponibilidad.GET(lectura("?recurso_id=r1&fecha=2027-09-07"));

    expect(llamarApi).toHaveBeenCalledWith(
      "/turnos/disponibilidad?recurso_id=r1&fecha=2027-09-07",
      { method: "GET" },
    );
  });

  it("cancelar no manda cuerpo con datos", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ ...TURNO, estado: "CANCELADO" });

    await rutaCancelacion.POST(lectura(), { params: { turnoId: "t1" } });

    expect(llamarApi).toHaveBeenCalledWith("/turnos/t1/cancelacion", {
      method: "POST",
      body: {},
    });
  });

  it("reprogramar manda el horario y **no** el estado", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue(TURNO);

    await rutaReprogramacion.POST(pedido({ inicio: "2027-09-07T19:00:00.000Z" }), {
      params: { turnoId: "t1" },
    });

    const [, opciones] = llamarApi.mock.calls[0] as [string, { body: Record<string, unknown> }];
    expect(opciones.body).toEqual({ inicio: "2027-09-07T19:00:00.000Z" });
    // Reprogramar no es un estado (HU-E7-02 RN-02), y esto lo fija en la frontera.
    expect(opciones.body).not.toHaveProperty("estado");
  });

  it("el rechazo por solapamiento llega con las palabras del backend", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockRejectedValue(
      new ErrorDeApi(422, "El horario seleccionado no está disponible.", "FranjaOcupada"),
    );

    const respuesta = await rutaTurnos.POST(pedido({ cliente_id: "cl1" }));

    expect(respuesta.status).toBe(422);
    expect(await respuesta.json()).toEqual({
      error: "FranjaOcupada",
      detalle: "El horario seleccionado no está disponible.",
    });
  });

  it("un 500 no filtra el detalle", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockRejectedValue(new ErrorDeApi(500, "asyncpg dice algo", "ErrorInterno"));

    const respuesta = await rutaTurnos.POST(pedido({ cliente_id: "cl1" }));

    expect(respuesta.status).toBe(500);
    expect(await respuesta.json()).toEqual({ error: "ErrorInterno" });
  });

  it("no ofrece un DELETE: un turno se cancela", () => {
    expect("DELETE" in rutaTurnos).toBe(false);
    expect("DELETE" in rutaTurno).toBe(false);
    expect("PUT" in rutaTurno).toBe(false);
  });
});

describe("los recursos", () => {
  it("las tres configuraciones son PUT porque reemplazan", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ id: "r1" });

    await rutaHorario.PUT(pedido({ patrones: [] }, "PUT"), { params: { recursoId: "r1" } });
    await rutaAsociados.PUT(pedido({ servicios: ["s1"] }, "PUT"), {
      params: { recursoId: "r1" },
    });
    await rutaEstado.PUT(pedido({ activo: false }, "PUT"), { params: { recursoId: "r1" } });

    expect(llamarApi.mock.calls.map(([ruta]) => ruta)).toEqual([
      "/recursos/r1/disponibilidad",
      "/recursos/r1/servicios",
      "/recursos/r1/estado",
    ]);
    expect(llamarApi.mock.calls.every(([, opciones]) => opciones.method === "PUT")).toBe(true);
  });

  it("los servicios agendables son una vista de la agenda, no el catalogo", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue([]);

    await rutaServicios.GET();

    expect(llamarApi).toHaveBeenCalledWith("/recursos/servicios", { method: "GET" });
  });

  it("el listado reenvía solo_activos", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ recursos: [] });

    await rutaRecursos.GET(lectura("?solo_activos=true"));

    expect(llamarApi).toHaveBeenCalledWith("/recursos?solo_activos=true", { method: "GET" });
  });

  it("la excepcion se agrega con POST y se quita con DELETE por fecha", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ id: "r1" });

    await rutaExcepciones.POST(pedido({ fecha: "2027-12-25", tipo: "BLOQUEO" }), {
      params: { recursoId: "r1" },
    });
    await rutaExcepcion.DELETE(lectura(), {
      params: { recursoId: "r1", fecha: "2027-12-25" },
    });

    expect(llamarApi.mock.calls[0]).toEqual([
      "/recursos/r1/excepciones",
      { method: "POST", body: { fecha: "2027-12-25", tipo: "BLOQUEO" } },
    ]);
    expect(llamarApi.mock.calls[1]).toEqual([
      "/recursos/r1/excepciones/2027-12-25",
      { method: "DELETE" },
    ]);
  });

  it("no ofrece un DELETE de recurso: se desactiva", () => {
    expect("DELETE" in rutaRecursos).toBe(false);
    expect("DELETE" in rutaEstado).toBe(false);
  });
});
