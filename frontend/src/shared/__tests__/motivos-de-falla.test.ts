/**
 * Por qué falló un envío de WhatsApp, dicho en castellano (U7, D-U7-7).
 *
 * El backend guarda un código de Meta (`131047`) o una clase corta (`INCIERTO`), nunca el texto del
 * error: la pantalla es quien lo traduce. Lo que no conoce se muestra con su código crudo para que
 * soporte pueda buscarlo, y nunca se inventa una explicación.
 */

import { describe, expect, it } from "vitest";

import { motivoDeFalla } from "@/shared/motivos-de-falla";

describe("motivoDeFalla", () => {
  it.each([
    ["131047", "Fuera de la ventana de 24 h y sin plantilla aprobada"],
    ["131026", "El número no usa WhatsApp"],
    ["131049", "Meta frenó el envío; se puede reintentar mañana"],
    ["132015", "La plantilla está pausada en Meta"],
    ["132016", "La plantilla está deshabilitada en Meta"],
    ["INCIERTO", "No sabemos si llegó: Meta no respondió"],
    ["COBRO_CERRADO", "No se envió: el cobro se cerró"],
  ])("traduce %s", (codigo, texto) => {
    expect(motivoDeFalla(codigo)).toBe(texto);
  });

  it.each([
    ["SATURADA", "Meta estaba saturado y no aceptó el mensaje"],
    ["RECHAZADO", "Meta rechazó el mensaje"],
    ["SIN_CANAL", "WhatsApp no está conectado"],
    ["ERROR", "Error inesperado al enviar"],
  ])("traduce la clase corta %s que arma el backend", (codigo, texto) => {
    expect(motivoDeFalla(codigo)).toBe(texto);
  });

  it("muestra el código crudo de lo que no conoce", () => {
    expect(motivoDeFalla("131050")).toBe("Código 131050");
  });

  it("sin código dice que no hay detalle", () => {
    expect(motivoDeFalla(null)).toBe("Sin detalle");
    expect(motivoDeFalla("")).toBe("Sin detalle");
  });
});
