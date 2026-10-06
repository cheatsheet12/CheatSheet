/**
 * La frontera del BFF para los cobros y las reglas de negocio.
 *
 * Las mismas dos propiedades de siempre —ninguna ruta llega al backend sin sesión, y el
 * query string se reenvía entero— más las tres que son de esta unidad:
 *
 * - **Los montos cruzan como texto.** Es el mismo invariante del épico 5 y por el mismo
 *   motivo: un `number` en el cuerpo es un float, y el float se come un centavo sin que
 *   nada falle.
 * - **No hay `DELETE` en ninguna de las dos.** Un cobro pagado es plata que entró: se
 *   reembolsa. Uno pendiente se cancela, y eso deja el motivo. Una regla se desactiva,
 *   porque una borrada deja la bitácora apuntando a algo que ya no existe.
 * - **El estado de una regla se manda entero, no como un toggle.** Dos pestañas abiertas
 *   sobre la misma regla no pueden dejarla en el estado contrario al que cada una vio.
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
const rutaCobros = await import("@/app/api/cobros/route");
const rutaCobro = await import("@/app/api/cobros/[cobroId]/route");
const rutaLink = await import("@/app/api/cobros/[cobroId]/link/route");
const rutaCancelacion = await import("@/app/api/cobros/[cobroId]/cancelacion/route");
const rutaReembolso = await import("@/app/api/cobros/[cobroId]/reembolso/route");
const rutaActualizacion = await import("@/app/api/cobros/[cobroId]/reembolso/actualizacion/route");
const rutaReembolsos = await import("@/app/api/cobros/[cobroId]/reembolsos/route");
const rutaCorreccion = await import(
  "@/app/api/cobros/[cobroId]/reembolsos/[reembolsoId]/correccion/route"
);
const rutaReglas = await import("@/app/api/reglas/route");
const rutaEscalamiento = await import("@/app/api/reglas/escalamiento/route");
const rutaEstadoDeRegla = await import("@/app/api/reglas/[reglaId]/estado/route");

const COBRO = { id: "co1", monto: "12500.10", estado: "PENDIENTE" };

function pedido(cuerpo: unknown = {}, metodo = "POST"): Request {
  return new Request("http://test/api/cobros", { method: metodo, body: JSON.stringify(cuerpo) });
}

function lectura(consulta = ""): Request {
  return new Request(`http://test/api/cobros${consulta}`, { method: "GET" });
}

afterEach(() => {
  cookieDeSesion = undefined;
  llamarApi.mockReset();
});

describe("sin sesión", () => {
  it("ninguna ruta llega al backend", async () => {
    const respuestas = await Promise.all([
      rutaCobros.GET(lectura()),
      rutaCobros.POST(pedido({ monto: "100" })),
      rutaCobro.GET(lectura(), { params: { cobroId: "co1" } }),
      rutaLink.POST(lectura(), { params: { cobroId: "co1" } }),
      rutaCancelacion.POST(pedido({ motivo: "x" }), { params: { cobroId: "co1" } }),
      rutaReembolso.POST(pedido({ monto: "100" }), { params: { cobroId: "co1" } }),
      rutaActualizacion.POST(pedido(), { params: { cobroId: "co1" } }),
      rutaReembolsos.POST(pedido({ monto: "100" }), { params: { cobroId: "co1" } }),
      rutaCorreccion.POST(pedido({ motivo: "x" }), {
        params: { cobroId: "co1", reembolsoId: "rb1" },
      }),
      rutaReglas.GET(),
      rutaEscalamiento.PUT(pedido({ pasos: [] }, "PUT")),
      rutaEstadoDeRegla.PUT(pedido({ activa: false }, "PUT"), { params: { reglaId: "rg1" } }),
    ]);

    expect(respuestas.map((respuesta) => respuesta.status)).toEqual(Array(12).fill(401));
    expect(llamarApi).not.toHaveBeenCalled();
  });
});

describe("los cobros", () => {
  it("reenvía el query string entero, sin conocer los filtros", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ cobros: [], metricas: {} });

    await rutaCobros.GET(lectura("?desde=2026-09-01&hasta=2026-09-30&estado=VENCIDO"));

    // Este archivo no aprende los nombres de los filtros: uno nuevo es un cambio, no dos.
    expect(llamarApi).toHaveBeenCalledWith(
      "/cobros?desde=2026-09-01&hasta=2026-09-30&estado=VENCIDO",
      { method: "GET" },
    );
  });

  it("el monto cruza como texto y no como numero", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue(COBRO);

    await rutaCobros.POST(pedido({ cliente_id: "cl1", monto: "12500.10", descripcion: "x" }));

    const [, opciones] = llamarApi.mock.calls[0] as [string, { body: { monto: unknown } }];
    expect(typeof opciones.body.monto).toBe("string");
    expect(opciones.body.monto).toBe("12500.10");
  });

  it("el POST reenvia la clave del pedido al backend (ADR-0013)", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue(COBRO);
    const conClave = new Request("http://test/api/cobros", {
      method: "POST",
      headers: { "X-Idempotency-Key": "6f1c1b6e-0000-4000-8000-000000000001" },
      body: JSON.stringify({ cliente_id: "cl1", monto: "100", descripcion: "x" }),
    });

    await rutaCobros.POST(conClave);

    expect(llamarApi).toHaveBeenCalledWith("/cobros", {
      method: "POST",
      body: { cliente_id: "cl1", monto: "100", descripcion: "x" },
      headers: { "X-Idempotency-Key": "6f1c1b6e-0000-4000-8000-000000000001" },
    });
  });

  it("sin encabezado el POST no inventa una clave", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue(COBRO);

    await rutaCobros.POST(pedido({ cliente_id: "cl1", monto: "100", descripcion: "x" }));

    const [, opciones] = llamarApi.mock.calls[0] as [string, Record<string, unknown>];
    expect("headers" in opciones).toBe(false);
  });

  it("el detalle usa el id de la ruta", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue(COBRO);

    await rutaCobro.GET(lectura(), { params: { cobroId: "co-1" } });

    expect(llamarApi).toHaveBeenCalledWith("/cobros/co-1", { method: "GET" });
  });

  it("regenerar el link no manda nada que elegir", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue(COBRO);

    await rutaLink.POST(lectura(), { params: { cobroId: "co1" } });

    expect(llamarApi).toHaveBeenCalledWith("/cobros/co1/link", { method: "POST", body: {} });
  });

  it("el motivo de la cancelación viaja en el cuerpo", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ ...COBRO, estado: "CANCELADO" });

    await rutaCancelacion.POST(pedido({ motivo: "El cliente pagó por transferencia" }), {
      params: { cobroId: "co1" },
    });

    expect(llamarApi).toHaveBeenCalledWith("/cobros/co1/cancelacion", {
      method: "POST",
      body: { motivo: "El cliente pagó por transferencia" },
    });
  });

  it("un cuerpo vacío no rompe la ruta: el backend decide si falta algo", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue(COBRO);

    await rutaCancelacion.POST(new Request("http://test/x", { method: "POST" }), {
      params: { cobroId: "co1" },
    });

    expect(llamarApi).toHaveBeenCalledWith("/cobros/co1/cancelacion", {
      method: "POST",
      body: {},
    });
  });

  it("el rechazo del reembolso llega con las palabras del backend", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockRejectedValue(
      new ErrorDeApi(
        422,
        "MercadoPago rechazó el reembolso. El cobro sigue figurando como pagado.",
        "ReembolsoRechazado",
      ),
    );

    const respuesta = await rutaReembolso.POST(pedido({ monto: "100" }), {
      params: { cobroId: "co1" },
    });

    expect(respuesta.status).toBe(422);
    expect(await respuesta.json()).toEqual({
      error: "ReembolsoRechazado",
      detalle: "MercadoPago rechazó el reembolso. El cobro sigue figurando como pagado.",
    });
  });

  it("un 502 no filtra el detalle: MercadoPago caído no es un rechazo", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockRejectedValue(
      new ErrorDeApi(502, "timeout contra api.mercadopago tras 3 intentos", "PasarelaNoDisponible"),
    );

    const respuesta = await rutaCobros.POST(pedido({ monto: "100" }));

    expect(respuesta.status).toBe(502);
    expect(await respuesta.json()).toEqual({ error: "PasarelaNoDisponible" });
  });

  it("no ofrece un DELETE: un cobro se cancela o se reembolsa", () => {
    expect("DELETE" in rutaCobros).toBe(false);
    expect("DELETE" in rutaCobro).toBe(false);
    // Ni un PUT en el detalle: cada acción tiene su ruta y su cuerpo.
    expect("PUT" in rutaCobro).toBe(false);
  });
});

describe("las reglas", () => {
  it("lista las reglas de la empresa", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ reglas: [] });

    await rutaReglas.GET();

    expect(llamarApi).toHaveBeenCalledWith("/reglas", { method: "GET" });
  });

  it("la cadena se reemplaza con un PUT, no se acumula", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ id: "rg1" });

    await rutaEscalamiento.PUT(
      pedido({ pasos: [{ dias: 3, canal: "WHATSAPP" }], prioridad: 0 }, "PUT"),
    );

    expect(llamarApi).toHaveBeenCalledWith("/reglas/escalamiento", {
      method: "PUT",
      body: { pasos: [{ dias: 3, canal: "WHATSAPP" }], prioridad: 0 },
    });
  });

  it("el estado se manda entero y con el id de la ruta", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ id: "rg1", activa: false });

    await rutaEstadoDeRegla.PUT(pedido({ activa: false }, "PUT"), {
      params: { reglaId: "rg-1" },
    });

    expect(llamarApi).toHaveBeenCalledWith("/reglas/rg-1/estado", {
      method: "PUT",
      body: { activa: false },
    });
  });

  it("no ofrece un DELETE: una regla se desactiva", () => {
    expect("DELETE" in rutaReglas).toBe(false);
    expect("DELETE" in rutaEstadoDeRegla).toBe(false);
    // Ni un POST en el listado: la única regla que este épico escribe es la de escalamiento,
    // y tiene su propia ruta porque **reemplaza**.
    expect("POST" in rutaReglas).toBe(false);
  });
});

describe("los reembolsos parciales y manuales", () => {
  it("«Actualizar estado» va a la ruta de actualización, sin cuerpo propio", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue(COBRO);

    await rutaActualizacion.POST(pedido(), { params: { cobroId: "co1" } });

    expect(llamarApi).toHaveBeenCalledWith("/cobros/co1/reembolso/actualizacion", {
      method: "POST",
      body: {},
    });
  });

  it("el registro manual cruza el monto como texto y la fecha como día", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue(COBRO);

    await rutaReembolsos.POST(
      pedido({ monto: "300.10", fecha: "2026-09-20", motivo: "Devolución" }),
      { params: { cobroId: "co1" } },
    );

    const [ruta, opciones] = llamarApi.mock.calls[0] as [
      string,
      { body: { monto: unknown; fecha: unknown } },
    ];
    expect(ruta).toBe("/cobros/co1/reembolsos");
    expect(opciones.body.monto).toBe("300.10");
    expect(opciones.body.fecha).toBe("2026-09-20");
  });

  it("la corrección usa el cobro y la fila de la ruta", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue(COBRO);

    await rutaCorreccion.POST(pedido({ motivo: "Se cargó por error" }), {
      params: { cobroId: "co1", reembolsoId: "rb1" },
    });

    expect(llamarApi).toHaveBeenCalledWith("/cobros/co1/reembolsos/rb1/correccion", {
      method: "POST",
      body: { motivo: "Se cargó por error" },
    });
  });

  it("un conflicto (409) lleva su mensaje al navegador", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockRejectedValue(
      new ErrorDeApi(409, "Este cobro ya tiene un reembolso en proceso.", "ReembolsoEnProceso"),
    );

    const respuesta = await rutaReembolso.POST(pedido({ monto: "100" }), {
      params: { cobroId: "co1" },
    });

    expect(respuesta.status).toBe(409);
    expect(await respuesta.json()).toEqual({
      error: "ReembolsoEnProceso",
      detalle: "Este cobro ya tiene un reembolso en proceso.",
    });
  });

  it("no ofrece un DELETE ni un PUT: una fila de reembolso no se edita ni se borra", () => {
    for (const ruta of [rutaActualizacion, rutaReembolsos, rutaCorreccion]) {
      expect("DELETE" in ruta).toBe(false);
      expect("PUT" in ruta).toBe(false);
      expect("PATCH" in ruta).toBe(false);
    }
  });
});
