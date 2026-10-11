/**
 * Dates, times and numbers under the user's preferences (caso 42).
 *
 * The time zone assertions use an instant deliberately chosen to fall on the other side
 * of midnight in Argentina: 01:30 UTC is the previous day at 22:30 in Buenos Aires. A
 * test at midday would pass with the time zone ignored entirely.
 */

import { describe, expect, it } from "vitest";

import {
  PREFERENCIAS_POR_DEFECTO,
  formatearFecha,
  formatearFechaHora,
  formatearHora,
  montoDesdeTexto,
  formatearNumero,
} from "@/shared/formato";

const MADRUGADA = "2026-08-18T01:30:00Z";

describe("formatearFechaHora", () => {
  it("respeta la zona horaria del usuario", () => {
    const buenosAires = formatearFechaHora(MADRUGADA, PREFERENCIAS_POR_DEFECTO);
    const utc = formatearFechaHora(MADRUGADA, { idioma: "es-AR", zonaHoraria: "UTC" });

    expect(buenosAires).toContain("17/8/26");
    expect(utc).toContain("18/8/26");
    expect(buenosAires).not.toBe(utc);
  });

  it("dos zonas argentinas distintas dan el mismo instante escrito igual", () => {
    // Argentina is one offset today. The point is that the code does not hardcode it:
    // it asks Intl, so the day the country changes this keeps being right.
    const cordoba = formatearFechaHora(MADRUGADA, {
      idioma: "es-AR",
      zonaHoraria: "America/Argentina/Cordoba",
    });

    expect(cordoba).toBe(formatearFechaHora(MADRUGADA, PREFERENCIAS_POR_DEFECTO));
  });

  it("sin fecha muestra un guion y no 'Invalid Date'", () => {
    expect(formatearFechaHora(null)).toBe("—");
    expect(formatearFechaHora("")).toBe("—");
    expect(formatearFechaHora("no-es-una-fecha")).toBe("—");
  });
});

describe("determinismo entre runtimes (hidratación)", () => {
  /*
   * The bug this guards against cost the whole page, not one label: Node's ICU writes
   * "p." U+00A0 "m." and Chrome's writes "p." U+0020 "m.", React saw two different
   * strings while hydrating and threw away the server HTML for the entire root.
   *
   * The assertion is on the characters rather than on the rendered string on purpose —
   * this suite runs under Node, so a test comparing against a literal would pass here
   * and still ship the mismatch to the browser.
   */
  it("ningun formateador devuelve espacios que el navegador escriba distinto", () => {
    const sospechosos = /[\u00a0\u202f]/;
    expect(sospechosos.test(formatearFechaHora(MADRUGADA, PREFERENCIAS_POR_DEFECTO))).toBe(false);
    expect(sospechosos.test(formatearFecha(MADRUGADA, PREFERENCIAS_POR_DEFECTO))).toBe(false);
    expect(sospechosos.test(formatearNumero("1234.5"))).toBe(false);
  });
});

describe("formatearFecha", () => {
  it("escribe solo el día, en la zona del usuario", () => {
    expect(formatearFecha(MADRUGADA, PREFERENCIAS_POR_DEFECTO)).toBe("17/8/26");
    expect(formatearFecha(null)).toBe("—");
  });
});

describe("formatearNumero", () => {
  it("usa la coma decimal del locale argentino", () => {
    expect(formatearNumero("1234.5")).toBe("1.234,50");
  });

  it("un valor que no es un número se devuelve tal cual", () => {
    // Better a raw string on screen than "NaN" where an amount should be.
    expect(formatearNumero("no-es-un-numero")).toBe("no-es-un-numero");
  });
});

describe("formatearHora", () => {
  it("escribe la hora en la zona del usuario, de 0 a 23", () => {
    // 01:30 UTC son las 22:30 del día anterior en Buenos Aires.
    expect(formatearHora(MADRUGADA, PREFERENCIAS_POR_DEFECTO)).toBe("22:30");
    expect(formatearHora("2026-08-18T21:05:00Z", PREFERENCIAS_POR_DEFECTO)).toBe("18:05");
  });

  it("sin instante muestra un guion", () => {
    expect(formatearHora(null)).toBe("—");
  });
});

describe("montoDesdeTexto", () => {
  // Visto en staging (TODO §29.3): «1234,56», el formato que usa todo el panel, daba «El monto
  // debe ser mayor a cero.» en Nuevo cobro. Con punto funcionaba.
  it.each([
    ["1234,56", "1234.56"],
    ["1.234,56", "1234.56"],
    ["1234.56", "1234.56"],
    ["12.500", "12500"],
    ["1.234.567,8", "1234567.8"],
    [" 15000 ", "15000"],
    ["$ 9.500,50", "9500.50"],
    ["0,5", "0.5"],
  ])("«%s» es %s", (entrada, esperado) => {
    expect(montoDesdeTexto(entrada)).toBe(esperado);
  });

  it.each(["", "abc", "12,3,4", "1,234.56.7", "-", ","])("«%s» no es un monto", (entrada) => {
    expect(montoDesdeTexto(entrada)).toBeNull();
  });
});
