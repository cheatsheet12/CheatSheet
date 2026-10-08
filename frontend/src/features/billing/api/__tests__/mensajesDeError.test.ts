import { describe, expect, it } from "vitest";

import { ErrorDeComprobante } from "../comprobante";
import { mensajeLegible } from "../mensajesDeError";

describe("mensajeLegible", () => {
  it("traduce ErrorInterno a una frase al validar", () => {
    const fallo = new ErrorDeComprobante("ErrorInterno", "ErrorInterno", null);
    expect(mensajeLegible(fallo, "validar")).toBe(
      "No pudimos validar el CUIT ahora. Probá de nuevo en un momento.",
    );
  });

  it("EntradaInvalida sin detalle no se muestra cruda", () => {
    const fallo = new ErrorDeComprobante("EntradaInvalida", "EntradaInvalida", null);
    expect(mensajeLegible(fallo, "validar")).not.toContain("EntradaInvalida");
    expect(mensajeLegible(fallo, "emitir")).not.toContain("EntradaInvalida");
  });

  it("el detalle del backend gana sobre cualquier código", () => {
    const fallo = new ErrorDeComprobante(
      "El CUIT ingresado no es válido.",
      "EntradaInvalida",
      "El CUIT ingresado no es válido.",
    );
    expect(mensajeLegible(fallo, "validar")).toBe("El CUIT ingresado no es válido.");
  });

  it("un código que sólo llegó como mensaje también se traduce", () => {
    expect(mensajeLegible(new ErrorDeComprobante("ErrorInterno"), "emitir")).toContain(
      "No pudimos emitir",
    );
  });

  it("una frase armada a mano se respeta", () => {
    expect(mensajeLegible(new ErrorDeComprobante("Algo pasó con ARCA."), "validar")).toBe(
      "Algo pasó con ARCA.",
    );
  });

  it("un código desconocido cae en la frase por defecto de la acción", () => {
    const fallo = new ErrorDeComprobante("CodigoNuevo", "CodigoNuevo", null);
    expect(mensajeLegible(fallo, "validar")).toContain("No pudimos validar el CUIT");
  });

  it("ARCA caída tiene su propia frase", () => {
    const fallo = new ErrorDeComprobante("ArcaNoDisponible", "ArcaNoDisponible", null);
    expect(mensajeLegible(fallo, "validar")).toContain("ARCA no responde");
  });

  it("un fallo que no vino del backend usa la frase por defecto", () => {
    expect(mensajeLegible(new TypeError("fetch failed"), "validar")).toContain(
      "No pudimos validar",
    );
  });
});
