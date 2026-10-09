/**
 * Los motivos de rechazo de Meta, en castellano (U6, caso 30).
 *
 * Meta devuelve un código (`PROMOTIONAL`); el administrador no tiene por qué saber qué dice. La
 * tabla es una cortesía de la pantalla: el texto literal de Meta (`detalle_meta`) se muestra
 * aparte, sin traducir.
 */

import { describe, expect, it } from "vitest";

import { traducirMotivoDeMeta } from "@/features/conversational";

describe("traducirMotivoDeMeta", () => {
  it.each([
    ["ABUSIVE_CONTENT", "Meta lo consideró abusivo"],
    ["INVALID_FORMAT", "Formato inválido: revisá variables y largo"],
    ["PROMOTIONAL", "Meta lo considera promocional: no corresponde a Utilidad"],
    ["INCORRECT_CATEGORY", "Meta lo considera promocional: no corresponde a Utilidad"],
    ["TAG_CONTENT_MISMATCH", "Meta lo considera promocional: no corresponde a Utilidad"],
    ["SCAM", "Meta lo consideró engañoso"],
  ])("%s se explica con su frase", (codigo, frase) => {
    expect(traducirMotivoDeMeta(codigo)).toBe(frase);
  });

  it("un código que no conoce se muestra tal cual llegó, sin inventarle una frase", () => {
    expect(traducirMotivoDeMeta("OTRO_MOTIVO")).toBe("Motivo informado por Meta: OTRO_MOTIVO");
  });

  it("sin motivo no hay nada que traducir", () => {
    expect(traducirMotivoDeMeta(null)).toBeNull();
  });
});
