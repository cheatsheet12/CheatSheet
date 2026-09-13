/**
 * La frontera del BFF de la reportería (HU-E10-01 … HU-E10-06).
 *
 * Las propiedades de siempre —ninguna ruta del panel llega al backend sin sesión, y el query
 * string se reenvía entero— más las dos que son de esta unidad:
 *
 * - **La ruta del contador NO exige sesión**, y es la única de todo el BFF. Este archivo lo
 *   afirma explícitamente: si alguien le agregara el guardia «por las dudas», el contador
 *   externo dejaría de poder entrar y nadie lo notaría hasta que llame.
 * - **La previsualización va por `GET`.** No crea nada (HU-E10-02 RN-03), y un verbo que
 *   sugiera lo contrario termina en una confirmación que la historia no pide.
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

const rutaTablero = await import("@/app/api/reporteria/tablero/route");
const rutaPrevisualizacion = await import("@/app/api/reporteria/previsualizacion/route");
const rutaReportes = await import("@/app/api/reporteria/reportes/route");
const rutaArchivoDeReporte = await import(
  "@/app/api/reporteria/reportes/[reporteId]/archivo/route"
);
const rutaPaquetes = await import("@/app/api/reporteria/paquetes/route");
const rutaArchivoDePaquete = await import(
  "@/app/api/reporteria/paquetes/[paqueteId]/archivo/route"
);
const rutaConfiguracion = await import("@/app/api/reporteria/configuracion/route");
const rutaContador = await import("@/app/api/reporteria/contador/route");
const rutaAcceso = await import("@/app/api/contador/[valor]/route");
const rutaDescargaDelContador = await import(
  "@/app/api/contador/[valor]/paquetes/[paqueteId]/route"
);

function pedido(cuerpo: unknown = {}, metodo = "POST"): Request {
  return new Request("http://test/api/reporteria", {
    method: metodo,
    body: JSON.stringify(cuerpo),
  });
}

function lectura(consulta = ""): Request {
  return new Request(`http://test/api/reporteria${consulta}`, { method: "GET" });
}

const ARCHIVO = {
  contenido: new ArrayBuffer(8),
  tipo: "text/csv; charset=utf-8",
  disposicion: 'attachment; filename="facturacion.csv"',
};

afterEach(() => {
  cookieDeSesion = undefined;
  llamarApi.mockReset();
  descargarBinario.mockReset();
});

describe("sin sesión", () => {
  it("ninguna ruta del panel llega al backend", async () => {
    const respuestas = await Promise.all([
      rutaTablero.GET(lectura()),
      rutaPrevisualizacion.GET(lectura("?tipo=COBROS")),
      rutaReportes.GET(),
      rutaReportes.POST(pedido({ tipo: "COBROS", formato: "CSV" })),
      rutaArchivoDeReporte.GET(lectura(), { params: { reporteId: "r1" } }),
      rutaPaquetes.GET(),
      rutaPaquetes.POST(pedido({})),
      rutaArchivoDePaquete.GET(lectura(), { params: { paqueteId: "p1" } }),
      rutaConfiguracion.GET(),
      rutaConfiguracion.PUT(pedido({}, "PUT")),
      rutaContador.POST(pedido({ email: "c@e.com" })),
      rutaContador.DELETE(),
    ]);

    expect(respuestas.map((respuesta) => respuesta.status)).toEqual(Array(12).fill(401));
    expect(llamarApi).not.toHaveBeenCalled();
    expect(descargarBinario).not.toHaveBeenCalled();
  });
});

describe("el tablero y la previsualización", () => {
  it("reenvían el query string entero, sin conocer los filtros", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({});

    await rutaTablero.GET(lectura("?desde=2026-03-01&hasta=2026-03-31"));

    expect(llamarApi).toHaveBeenCalledWith(
      "/reporteria/tablero?desde=2026-03-01&hasta=2026-03-31",
      { method: "GET" },
    );
  });

  it("la previsualización usa GET: no crea nada", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({});

    await rutaPrevisualizacion.GET(lectura("?tipo=FACTURACION"));

    expect(llamarApi).toHaveBeenCalledWith("/reporteria/previsualizacion?tipo=FACTURACION", {
      method: "GET",
    });
  });
});

describe("los reportes", () => {
  it("la generación lleva el período en la consulta y el tipo en el cuerpo", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ id: "r1" });

    const conRango = new Request("http://test/api/reporteria/reportes?desde=2026-03-01", {
      method: "POST",
      body: JSON.stringify({ tipo: "FACTURACION", formato: "CSV" }),
    });
    await rutaReportes.POST(conRango);

    expect(llamarApi).toHaveBeenCalledWith("/reporteria/reportes?desde=2026-03-01", {
      method: "POST",
      body: { tipo: "FACTURACION", formato: "CSV" },
    });
  });

  it("el archivo sale como bytes, con el nombre que puso el backend", async () => {
    cookieDeSesion = "un-access-token";
    descargarBinario.mockResolvedValue(ARCHIVO);

    const respuesta = await rutaArchivoDeReporte.GET(lectura(), { params: { reporteId: "r1" } });

    expect(descargarBinario).toHaveBeenCalledWith("/reporteria/reportes/r1/archivo");
    expect(respuesta.headers.get("Content-Type")).toBe("text/csv; charset=utf-8");
    expect(respuesta.headers.get("Content-Disposition")).toContain("attachment");
  });

  it("un reporte que no está listo contesta con la frase del backend", async () => {
    cookieDeSesion = "un-access-token";
    const { ErrorDeApi } = await import("@/lib/api");
    descargarBinario.mockRejectedValue(
      new ErrorDeApi(409, "El reporte todavía no está disponible para descargar"),
    );

    const respuesta = await rutaArchivoDeReporte.GET(lectura(), { params: { reporteId: "r1" } });

    expect(respuesta.status).toBe(409);
  });
});

describe("el paquete y el contador", () => {
  it("el paquete de prueba manda el cuerpo tal cual", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({ id: "p1" });

    await rutaPaquetes.POST(pedido({ anio: 2026, mes: 2 }));

    expect(llamarApi).toHaveBeenCalledWith("/reporteria/paquetes", {
      method: "POST",
      body: { anio: 2026, mes: 2 },
    });
  });

  it("revocar el acceso es un DELETE sin cuerpo", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({});

    await rutaContador.DELETE();

    expect(llamarApi).toHaveBeenCalledWith("/reporteria/contador", { method: "DELETE" });
  });

  it("la configuración se guarda entera con un PUT", async () => {
    cookieDeSesion = "un-access-token";
    llamarApi.mockResolvedValue({});

    await rutaConfiguracion.PUT(pedido({ dia_de_envio: 10, activo: true }, "PUT"));

    expect(llamarApi).toHaveBeenCalledWith("/reporteria/configuracion", {
      method: "PUT",
      body: { dia_de_envio: 10, activo: true },
    });
  });
});

describe("la ruta del contador externo", () => {
  it("**no** exige sesión: la credencial es el enlace", async () => {
    llamarApi.mockResolvedValue({ vence: "2026-05-05T00:00:00Z" });

    const respuesta = await rutaAcceso.GET(lectura(), { params: { valor: "abc" } });

    expect(respuesta.status).toBe(200);
    expect(llamarApi).toHaveBeenCalledWith("/contador/abc");
  });

  it("escapa el valor del enlace antes de armar la URL", async () => {
    llamarApi.mockResolvedValue({});

    await rutaAcceso.GET(lectura(), { params: { valor: "a/b c" } });

    expect(llamarApi).toHaveBeenCalledWith("/contador/a%2Fb%20c");
  });

  it("un enlace revocado contesta la frase de la historia", async () => {
    const { ErrorDeApi } = await import("@/lib/api");
    llamarApi.mockRejectedValue(
      new ErrorDeApi(422, "El acceso a este paquete ya no está disponible."),
    );

    const respuesta = await rutaAcceso.GET(lectura(), { params: { valor: "abc" } });
    const cuerpo = (await respuesta.json()) as { detalle?: string };

    expect(respuesta.status).toBe(422);
    expect(cuerpo.detalle).toBe("El acceso a este paquete ya no está disponible.");
  });

  it("la descarga del contador tampoco exige sesión y sale como bytes", async () => {
    descargarBinario.mockResolvedValue({ ...ARCHIVO, tipo: "application/zip" });

    const respuesta = await rutaDescargaDelContador.GET(lectura(), {
      params: { valor: "abc", paqueteId: "p1" },
    });

    expect(descargarBinario).toHaveBeenCalledWith("/contador/abc/paquetes/p1");
    expect(respuesta.headers.get("Content-Type")).toBe("application/zip");
  });
});
