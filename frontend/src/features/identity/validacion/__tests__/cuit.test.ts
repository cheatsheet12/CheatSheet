/**
 * The browser-side CUIT check.
 *
 * It must agree with `contexts/identity/domain/valores.py`, which is the authority. The
 * cases here are the same ones that file's tests use, on purpose: two implementations of
 * one published algorithm are only safe while they are checked against the same inputs.
 */

import { describe, expect, it } from "vitest";

import { errorDeCuit, esCuitValido, formatearCuit, normalizarCuit } from "@/features/identity";

/** 30-71234567-1 — check digit computed with ARCA's weights. */
const VALIDO = "30712345671";

describe("esCuitValido", () => {
  it("acepta un CUIT con dígito verificador correcto", () => {
    expect(esCuitValido(VALIDO)).toBe(true);
  });

  it("rechaza el mismo número con el último dígito cambiado", () => {
    expect(esCuitValido("30712345670")).toBe(false);
  });

  it.each(["30-71234567-1", "30 71234567 1", "30.71234567.1"])(
    "acepta la notación con separadores: %s",
    (escrito) => {
      expect(esCuitValido(escrito)).toBe(true);
    },
  );

  it.each(["3071234567", "307123456712", "", "abcdefghijk"])(
    "rechaza lo que no son once dígitos: %s",
    (escrito) => {
      expect(esCuitValido(escrito)).toBe(false);
    },
  );
});

describe("errorDeCuit", () => {
  it("no grita cuando el campo está vacío", () => {
    expect(errorDeCuit("")).toBeNull();
  });

  it("pide los once dígitos cuando faltan", () => {
    expect(errorDeCuit("3071234")).toBe("Ingresá los 11 dígitos del CUIT.");
  });

  it("avisa del dígito verificador con el mensaje de la especificación", () => {
    expect(errorDeCuit("30712345670")).toBe(
      "El CUIT no supera la validación del dígito verificador.",
    );
  });

  it("no reporta error sobre un CUIT válido", () => {
    expect(errorDeCuit(VALIDO)).toBeNull();
  });
});

describe("normalizarCuit y formatearCuit", () => {
  it("normalizar deja solo dígitos", () => {
    expect(normalizarCuit("30-71234567-1")).toBe(VALIDO);
  });

  it("formatear lo escribe como lo lee una persona", () => {
    expect(formatearCuit(VALIDO)).toBe("30-71234567-1");
  });

  it("formatear no rompe lo que todavía está incompleto", () => {
    expect(formatearCuit("3071")).toBe("3071");
  });
});
