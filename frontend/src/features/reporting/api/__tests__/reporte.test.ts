/**
 * El cliente de API del tablero y de los reportes (HU-E10-01 … HU-E10-03).
 *
 * Tres cosas se afirman acá y en ningún otro lado del frontend:
 *
 * - **los importes viajan como texto**, y la manera de romperlo sin darse cuenta es un
 *   `Number()` puesto para «normalizar»: lo que vuelve se compara carácter por carácter;
 * - **la previsualización va por `GET`**, porque no crea nada (HU-E10-02 RN-03). Un `POST`
 *   sugeriría lo contrario y alguien la pondría detrás de una confirmación;
 * - **el `detalle` del backend gana sobre cualquier texto local**: en un 422 esa frase es la
 *   que escribió la historia, palabra por palabra.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ErrorDeReporte,
  FORMATOS_POR_TIPO,
  MENSAJE_SIN_DATOS,
  generarReporte,
  listarReportes,
  previsualizar,
  urlDeReporte,
  verTablero,
} from "@/features/reporting";
import type { TableroRespuesta } from "@/features/reporting";

const TABLERO: TableroRespuesta = {
  desde: "2026-03-01",
  hasta: "2026-03-31",
  facturado: { valor: "12500.55", anterior: "10000.00", variacion: "25.0" },
  cobrado: { valor: "8000.00", anterior: "0.00", variacion: null },
  turnos: { valor: "12", anterior: "10", variacion: "20.0" },
  operaciones: { valor: "340", anterior: "300", variacion: "13.3" },
  por_tipo: { FACTURA_B: "12500.55" },
  por_semana: { "2026-W10": "12500.55" },
  pendiente: "1500.00",
  en_mora: "500.00",
  sin_actividad: false,
};

function respuesta(cuerpo: unknown, ok = true, status = 200): Response {
  return { ok, status, json: () => Promise.resolve(cuerpo) } as unknown as Response;
}

function espiarFetch(...respuestas: readonly Response[]): ReturnType<typeof vi.fn> {
  const espia = vi.fn();
  for (const una of respuestas) {
    espia.mockResolvedValueOnce(una);
  }
  vi.stubGlobal("fetch", espia);
  return espia;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("verTablero", () => {
  it("devuelve los importes tal como llegaron, sin convertirlos", async () => {
    espiarFetch(respuesta(TABLERO));

    const tablero = await verTablero();

    expect(tablero.facturado.valor).toBe("12500.55");
    expect(typeof tablero.facturado.valor).toBe("string");
  });

  it("mantiene el null de la variación", async () => {
    espiarFetch(respuesta(TABLERO));

    const tablero = await verTablero();

    // `null` y no cero: «creció 0%» y «no hay con qué comparar» son cosas distintas.
    expect(tablero.cobrado.variacion).toBeNull();
  });

  it("manda el período en el query string", async () => {
    const espia = espiarFetch(respuesta(TABLERO));

    await verTablero({ desde: "2026-03-01", hasta: "2026-03-31" });

    expect(espia).toHaveBeenCalledWith(
      "/api/reporteria/tablero?desde=2026-03-01&hasta=2026-03-31",
      expect.anything(),
    );
  });

  it("no manda un filtro vacío", async () => {
    const espia = espiarFetch(respuesta(TABLERO));

    await verTablero({ desde: "", hasta: "2026-03-31" });

    expect(espia).toHaveBeenCalledWith(
      "/api/reporteria/tablero?hasta=2026-03-31",
      expect.anything(),
    );
  });
});

describe("previsualizar", () => {
  it("va por GET, porque no crea nada", async () => {
    const espia = espiarFetch(
      respuesta({
        tipo: "FACTURACION",
        desde: "2026-03-01",
        hasta: "2026-03-31",
        cantidad: 7,
        total: "42000.00",
        hay_datos: true,
      }),
    );

    await previsualizar("FACTURACION", { desde: "2026-03-01" });

    const [url, opciones] = espia.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/reporteria/previsualizacion?");
    expect(url).toContain("tipo=FACTURACION");
    expect(opciones.method).toBeUndefined();
  });
});

describe("generarReporte", () => {
  it("manda tipo y formato en el cuerpo", async () => {
    const espia = espiarFetch(
      respuesta({
        id: "r1",
        tipo: "COBROS",
        formato: "CSV",
        desde: "2026-03-01",
        hasta: "2026-03-31",
        estado: "LISTO",
        descargable: true,
      }),
    );

    await generarReporte("COBROS", "CSV");

    const [, opciones] = espia.mock.calls[0] as [string, RequestInit];
    expect(opciones.method).toBe("POST");
    expect(opciones.body).toBe(JSON.stringify({ tipo: "COBROS", formato: "CSV" }));
  });

  it("propaga la frase del backend cuando el período no tiene datos", async () => {
    espiarFetch(
      respuesta({ error: "SinDatosEnElPeriodo", detalle: MENSAJE_SIN_DATOS }, false, 422),
    );

    await expect(generarReporte("FACTURACION", "CSV")).rejects.toThrow(MENSAJE_SIN_DATOS);
  });

  it("levanta un ErrorDeReporte con un cuerpo que no es JSON", async () => {
    const rota = {
      ok: false,
      status: 500,
      json: () => Promise.reject(new Error("no es json")),
    } as unknown as Response;
    espiarFetch(rota);

    await expect(generarReporte("FACTURACION", "CSV")).rejects.toBeInstanceOf(ErrorDeReporte);
  });
});

describe("listarReportes", () => {
  it("trae el historial", async () => {
    espiarFetch(respuesta({ reportes: [] }));

    expect(await listarReportes()).toEqual({ reportes: [] });
  });

  it("falla con el código cuando no hay detalle", async () => {
    espiarFetch(respuesta({ error: "NoAutenticado" }, false, 401));

    await expect(listarReportes()).rejects.toThrow("NoAutenticado");
  });
});

describe("la tabla de formatos", () => {
  it("no ofrece un resumen ejecutivo en CSV", () => {
    // Cuatro números sin gráfico: el backend lo rechaza y ofrecerlo sería hacer que alguien
    // lo descubra apretando el botón.
    expect(FORMATOS_POR_TIPO.RESUMEN_EJECUTIVO).toEqual(["PDF"]);
    expect(FORMATOS_POR_TIPO.COBROS).toEqual(["CSV"]);
  });
});

describe("urlDeReporte", () => {
  it("apunta al BFF, no al backend", () => {
    expect(urlDeReporte("r1")).toBe("/api/reporteria/reportes/r1/archivo");
  });
});
