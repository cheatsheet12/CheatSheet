/**
 * El cliente de API de PAN-CFG-RN.
 *
 * Lo que se prueba acá y en ningún otro lado es **`pasosDe`**, que es la única función del
 * frontend que interpreta un JSONB. La configuración de una regla es un objeto libre en la
 * base (decisión D24: la validación vive en el dominio, no en el esquema), así que la
 * pantalla puede recibir cualquier cosa — una fila escrita a mano, una regla de otra versión.
 *
 * Devolver `[]` en vez de romper es la decisión que hace que eso sea una regla vacía y
 * editable en lugar de una página en blanco.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ErrorDeRegla,
  cambiarEstadoDeRegla,
  configurarEscalamiento,
  listarReglas,
  pasosDe,
} from "@/features/payments";
import type { ReglaDeNegocio } from "@/features/payments";

const REGLA: ReglaDeNegocio = {
  id: "rg1",
  tipo: "ESCALAMIENTO_DE_COBRO",
  configuracion: { pasos: [{ dias: 3, canal: "WHATSAPP" }] },
  prioridad: 0,
  activa: true,
  created_at: "2026-09-07T12:00:00Z",
  updated_at: null,
};

function respuesta(cuerpo: unknown, ok = true, status = 200): Response {
  return { ok, status, json: () => Promise.resolve(cuerpo) } as unknown as Response;
}

function conConfiguracion(configuracion: Record<string, unknown>): ReglaDeNegocio {
  return { ...REGLA, configuracion };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("listarReglas", () => {
  it("no cachea la configuracion vigente", async () => {
    const espia = vi.fn().mockResolvedValue(respuesta({ reglas: [REGLA] }));
    vi.stubGlobal("fetch", espia);

    const listado = await listarReglas();

    expect(listado.reglas).toHaveLength(1);
    expect(espia).toHaveBeenCalledWith("/api/reglas", { cache: "no-store" });
  });

  it("falla con el codigo cuando no hay detalle", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(respuesta({ error: "NoAutenticado" }, false, 401)),
    );

    await expect(listarReglas()).rejects.toThrow("NoAutenticado");
  });

  it("no se rompe con un cuerpo que no es JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: () => Promise.reject(new Error("no es JSON")),
      } as unknown as Response),
    );

    await expect(listarReglas()).rejects.toBeInstanceOf(ErrorDeRegla);
  });
});

describe("configurarEscalamiento", () => {
  it("es un PUT: la empresa tiene una cadena, no un catalogo de cadenas", async () => {
    const espia = vi.fn().mockResolvedValue(respuesta(REGLA));
    vi.stubGlobal("fetch", espia);

    await configurarEscalamiento([{ dias: 3, canal: "WHATSAPP" }]);

    const [ruta, opciones] = espia.mock.calls[0] as [string, RequestInit];
    expect(ruta).toBe("/api/reglas/escalamiento");
    expect(opciones.method).toBe("PUT");
    expect(opciones.body).toBe(
      JSON.stringify({ pasos: [{ dias: 3, canal: "WHATSAPP" }], prioridad: 0 }),
    );
  });

  it("propaga el rechazo del dominio con su frase", async () => {
    const frase = "Los días de escalamiento deben ser mayores a cero.";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(respuesta({ error: "ReglaInvalida", detalle: frase }, false, 422)),
    );

    await expect(configurarEscalamiento([{ dias: 0, canal: "WHATSAPP" }])).rejects.toThrow(frase);
  });
});

describe("cambiarEstadoDeRegla", () => {
  it("manda el estado deseado y no un toggle", async () => {
    const espia = vi.fn().mockResolvedValue(respuesta({ ...REGLA, activa: false }));
    vi.stubGlobal("fetch", espia);

    await cambiarEstadoDeRegla("rg1", false);

    const [ruta, opciones] = espia.mock.calls[0] as [string, RequestInit];
    // El estado deseado y no «alterná»: dos pestañas abiertas sobre la misma regla no
    // pueden dejarla en el estado contrario al que cada una vio.
    expect(ruta).toBe("/api/reglas/rg1/estado");
    expect(opciones.body).toBe(JSON.stringify({ activa: false }));
  });
});

describe("pasosDe", () => {
  it("lee la cadena guardada", () => {
    expect(pasosDe(REGLA)).toEqual([{ dias: 3, canal: "WHATSAPP" }]);
  });

  it("devuelve vacio cuando la configuracion no tiene pasos", () => {
    expect(pasosDe(conConfiguracion({}))).toEqual([]);
    expect(pasosDe(conConfiguracion({ pasos: "tres" }))).toEqual([]);
  });

  it("descarta el paso mal formado y se queda con los buenos", () => {
    // Una fila escrita a mano en la base no tiene por qué dejar sin pantalla a la empresa.
    const reglas = conConfiguracion({
      pasos: [
        { dias: 3, canal: "WHATSAPP" },
        null,
        "siete",
        { dias: "siete", canal: "WHATSAPP" },
        { dias: 7 },
        { dias: 15, canal: "EMAIL" },
      ],
    });

    expect(pasosDe(reglas)).toEqual([
      { dias: 3, canal: "WHATSAPP" },
      { dias: 15, canal: "EMAIL" },
    ]);
  });
});
