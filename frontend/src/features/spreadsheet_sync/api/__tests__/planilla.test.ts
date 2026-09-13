/**
 * El cliente de PAN-ING-01, y sobre todo las dos negativas que ocurren sin red.
 *
 * HU-E3-03 escribe sus dos rechazos palabra por palabra. Que el usuario lea exactamente
 * esa frase —y que la lea **antes** de que se suban 30 MB— es el criterio de aceptación,
 * no un detalle de implementación.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ErrorDePlanilla,
  LIMITE_TAMANO_BYTES,
  MENSAJE_ARCHIVO_DEMASIADO_GRANDE,
  MENSAJE_FORMATO_NO_ACEPTADO,
  desvincularPlanilla,
  listarPlanillas,
  subirPlanilla,
  validarArchivo,
} from "../planilla";

function archivo(nombre: string, tamano = 10): File {
  const contenido = new Uint8Array(tamano);
  return new File([contenido], nombre);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("validarArchivo", () => {
  it.each([".pdf", ".txt", ".exe", ""])(
    "rechaza la extension %s con el texto de la historia",
    (ext) => {
      expect(() => validarArchivo(archivo(`clientes${ext}`))).toThrow(MENSAJE_FORMATO_NO_ACEPTADO);
    },
  );

  it.each(["clientes.xlsx", "Clientes.XLSX", "datos.csv", "viejo.xls"])("acepta %s", (nombre) => {
    expect(() => validarArchivo(archivo(nombre))).not.toThrow();
  });

  it("rechaza un archivo de mas de 25 MB con el texto de la historia", () => {
    expect(() => validarArchivo(archivo("grande.xlsx", LIMITE_TAMANO_BYTES + 1))).toThrow(
      MENSAJE_ARCHIVO_DEMASIADO_GRANDE,
    );
  });
});

describe("subirPlanilla", () => {
  it("no toca la red cuando el archivo no pasa la validacion", async () => {
    const fetchEspia = vi.fn();
    vi.stubGlobal("fetch", fetchEspia);

    await expect(subirPlanilla(archivo("clientes.pdf"))).rejects.toBeInstanceOf(ErrorDePlanilla);
    expect(fetchEspia).not.toHaveBeenCalled();
  });

  it("manda el nombre codificado en la query y los bytes en el cuerpo", async () => {
    const fetchEspia = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ id: "v1", nombre_archivo: "clientes año.xlsx" }),
    });
    vi.stubGlobal("fetch", fetchEspia);

    await subirPlanilla(archivo("clientes año.xlsx"));

    const [url, opciones] = fetchEspia.mock.calls[0] as [string, RequestInit];
    // El acento viaja codificado: por eso el nombre va en la query y no en un header.
    expect(url).toBe("/api/planillas/archivo?nombre=clientes%20a%C3%B1o.xlsx");
    expect(opciones.method).toBe("POST");
  });

  it("prefiere el detalle del backend sobre el codigo", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        json: async () => ({
          error: "FormatoDePlanillaNoSoportado",
          detalle: MENSAJE_FORMATO_NO_ACEPTADO,
        }),
      }),
    );

    await expect(subirPlanilla(archivo("clientes.xlsx"))).rejects.toThrow(
      MENSAJE_FORMATO_NO_ACEPTADO,
    );
  });
});

describe("listar y desvincular", () => {
  it("devuelve el listado", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ vinculos: [] }) }),
    );

    await expect(listarPlanillas()).resolves.toEqual({ vinculos: [] });
  });

  it("falla con un mensaje utilizable cuando el backend rechaza", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, json: async () => ({ error: "NoAutenticado" }) }),
    );

    await expect(desvincularPlanilla("v1")).rejects.toThrow("NoAutenticado");
  });
});
