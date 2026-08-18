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
