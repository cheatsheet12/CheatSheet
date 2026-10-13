/**
 * Cómo se lee una acción de la bitácora (#175).
 *
 * El backend registra identificadores sin tildes (`registrar_excepcion`) y alguno en inglés
 * (`marcar_turno_no_show`). La pantalla los muestra en español escrito como corresponde, y el
 * identificador original sigue en chico, para buscarlo y copiarlo.
 */

import { describe, expect, it } from "vitest";

import { nombreDeAccion } from "../formato";

describe("nombreDeAccion", () => {
  it("pone las tildes que el identificador no lleva", () => {
    expect(nombreDeAccion("registrar_excepcion")).toBe("Registrar excepción");
    expect(nombreDeAccion("completar_datos_de_empresa")).toBe("Completar datos de empresa");
    expect(nombreDeAccion("revocar_sesion")).toBe("Revocar sesión");
    expect(nombreDeAccion("autorizar_comprobante")).toBe("Autorizar comprobante");
    expect(nombreDeAccion("conciliacion_de_cobros")).toBe("Conciliación de cobros");
  });

  it("dice la inasistencia en español", () => {
    expect(nombreDeAccion("marcar_turno_no_show")).toBe("Marcar turno como no presentado");
  });

  it("deja igual lo que ya se lee bien", () => {
    expect(nombreDeAccion("cliente_desactivado")).toBe("Cliente desactivado");
    expect(nombreDeAccion("reservar_turno")).toBe("Reservar turno");
  });
});
