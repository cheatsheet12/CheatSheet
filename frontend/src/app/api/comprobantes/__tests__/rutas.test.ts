/**
 * La frontera del BFF para los comprobantes.
 *
 * Las mismas dos propiedades de siempre —ninguna ruta llega al backend sin sesión, y el
 * query string se reenvía entero— más las dos que son de esta unidad:
 *
 * - **Los montos cruzan como texto.** El día que alguien los convierta a `number` «para
 *   que sea más prolijo», el error binario entra al sistema sin que nada falle.
 * - **No hay `DELETE` ni `PUT`.** Un comprobante con CAE es un registro legal: se anula con
 *   una nota de crédito, que es otro documento. El backend no otorga ninguno de los dos.
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
const descargarBinario = vi.fn();
vi.mock("@/lib/api", async () => {
  const real = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...real,
    llamarApi: (...args: unknown[]) => llamarApi(...args),
    descargarBinario: (...args: unknown[]) => descargarBinario(...args),
  };
});

const { ErrorDeApi } = await import("@/lib/api");
const rutaBase = await import("@/app/api/comprobantes/route");
const rutaDetalle = await import("@/app/api/comprobantes/[comprobanteId]/route");
const rutaReceptor = await import("@/app/api/comprobantes/receptores/[cuit]/route");
const rutaPdf = await import("@/app/api/comprobantes/[comprobanteId]/pdf/route");

const COMPROBANTE = { id: "c1", tipo: "FACTURA_A", total: "2420.00" };

function pedido(cuerpo: unknown = {}): Request {
  return new Request("http://test/api/comprobantes", {
    method: "POST",
    body: JSON.stringify(cuerpo),
  });
}

function listado(consulta = ""): Request {
  return new Request(`http://test/api/comprobantes${consulta}`, { method: "GET" });
}

afterEach(() => {
  cookieDeSesion = undefined;
  llamarApi.mockReset();
  descargarBinario.mockReset();
});

describe("sin sesión", () => {
  it("ninguna ruta llega al backend", async () => {
    const respuestas = await Promise.all([
      rutaBase.GET(listado()),
      rutaBase.POST(pedido({ tipo: "FACTURA_A" })),
      rutaDetalle.GET(listado(), { params: { comprobanteId: "c1" } }),
      rutaReceptor.GET(listado(), { params: { cuit: "30712345671" } }),
      rutaPdf.GET(listado(), { params: { comprobanteId: "c1" } }),
    ]);

    expect(respuestas.map((respuesta) => respuesta.status)).toEqual(Array(5).fill(401));
    expect(llamarApi).not.toHaveBeenCalled();
    expect(descargarBinario).not.toHaveBeenCalled();
  });
});

describe("con sesión", () => {
  it("reenvía el query string entero, sin conocer los filtros", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ comprobantes: [] });

    await rutaBase.GET(listado("?desde=2026-09-01&tipo=FACTURA_A&estado=AUTORIZADO"));

    expect(llamarApi).toHaveBeenCalledWith(
      "/comprobantes?desde=2026-09-01&tipo=FACTURA_A&estado=AUTORIZADO",
      { method: "GET" },
    );
  });

  it("los montos cruzan como texto y no como numero", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue(COMPROBANTE);

    await rutaBase.POST(
      pedido({
        tipo: "FACTURA_A",
        items: [{ descripcion: "Corte", cantidad: "2", precio_unitario: "1000.00" }],
      }),
    );

    const [, opciones] = llamarApi.mock.calls[0] as [
      string,
      { body: { items: { precio_unitario: unknown }[] } },
    ];
    expect(typeof opciones.body.items[0]?.precio_unitario).toBe("string");
    expect(opciones.body.items[0]?.precio_unitario).toBe("1000.00");
  });

  it("el detalle usa el id de la ruta", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue(COMPROBANTE);

    await rutaDetalle.GET(listado(), { params: { comprobanteId: "c-1" } });

    expect(llamarApi).toHaveBeenCalledWith("/comprobantes/c-1", { method: "GET" });
  });

  it("el CUIT se escapa antes de entrar en la ruta", async () => {
    // Llega de un campo de texto: es entrada no confiable como cualquier otra, y un CUIT
    // con una barra armaría una ruta que no es la que este archivo cree que arma.
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ nombre: "Acme", tipos_disponibles: [] });

    await rutaReceptor.GET(listado(), { params: { cuit: "30/71234567" } });

    expect(llamarApi).toHaveBeenCalledWith("/comprobantes/receptores/30%2F71234567", {
      method: "GET",
    });
  });

  it("un 422 llega con las palabras de ARCA, que son las que se muestran", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockRejectedValue(
      new ErrorDeApi(
        422,
        "Error 10016: el comprobante no cumple la resolucion general vigente",
        "EntradaInvalida",
      ),
    );

    const respuesta = await rutaBase.POST(pedido({ tipo: "FACTURA_A" }));

    expect(respuesta.status).toBe(422);
    expect(await respuesta.json()).toEqual({
      error: "EntradaInvalida",
      detalle: "Error 10016: el comprobante no cumple la resolucion general vigente",
    });
  });

  it("un 503 no filtra el detalle: ARCA caída no es un rechazo", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockRejectedValue(
      new ErrorDeApi(503, "wsfe timeout tras 3 intentos", "ArcaNoDisponible"),
    );

    const respuesta = await rutaBase.POST(pedido({ tipo: "FACTURA_A" }));

    expect(respuesta.status).toBe(503);
    expect(await respuesta.json()).toEqual({ error: "ArcaNoDisponible" });
  });
});

describe("el PDF", () => {
  it("devuelve los bytes con el tipo y el nombre que puso el backend", async () => {
    cookieDeSesion = "un-access-token";
    descargarBinario.mockResolvedValue({
      contenido: new TextEncoder().encode("%PDF-1.4").buffer,
      tipo: "application/pdf",
      disposicion: 'inline; filename="0001-00000123.pdf"',
    });

    const respuesta = await rutaPdf.GET(listado(), { params: { comprobanteId: "c1" } });

    expect(respuesta.status).toBe(200);
    expect(respuesta.headers.get("Content-Type")).toBe("application/pdf");
    expect(respuesta.headers.get("Content-Disposition")).toContain("0001-00000123.pdf");
    expect(descargarBinario).toHaveBeenCalledWith("/comprobantes/c1/pdf");
  });

  it("un comprobante sin autorizar contesta 422 con la frase, no una pestaña vacia", async () => {
    cookieDeSesion = "un-access-token";
    descargarBinario.mockRejectedValue(
      new ErrorDeApi(
        422,
        "Este comprobante todavia no fue autorizado por ARCA, asi que no tiene representacion imprimible.",
        "EntradaInvalida",
      ),
    );

    const respuesta = await rutaPdf.GET(listado(), { params: { comprobanteId: "c1" } });

    expect(respuesta.status).toBe(422);
    expect(await respuesta.json()).toEqual({
      error: "EntradaInvalida",
      detalle:
        "Este comprobante todavia no fue autorizado por ARCA, asi que no tiene representacion imprimible.",
    });
  });
});

describe("lo que no existe", () => {
  it("no hay DELETE ni PUT: un comprobante con CAE es un registro legal", () => {
    expect("DELETE" in rutaBase).toBe(false);
    expect("PUT" in rutaBase).toBe(false);
    expect("DELETE" in rutaDetalle).toBe(false);
    expect("PUT" in rutaDetalle).toBe(false);
  });
});
