/**
 * @vitest-environment jsdom
 *
 * The footer links to both public pages (HU-E1-03 RN-04, HU-E1-08 RN-06; plan case 9).
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { EnlacesLegales } from "../EnlacesLegales";

afterEach(cleanup);

describe("EnlacesLegales", () => {
  it("enlaza los términos y la política, cada uno a su ruta estable", () => {
    render(<EnlacesLegales />);

    const terminos = screen.getByRole("link", { name: "Términos y Condiciones" });
    const privacidad = screen.getByRole("link", { name: "Política de Privacidad" });
    expect(terminos.getAttribute("href")).toBe("/terminos");
    expect(privacidad.getAttribute("href")).toBe("/privacidad");
  });

  it("se abren en otra pestaña para no perder lo que la persona estaba completando", () => {
    render(<EnlacesLegales />);

    for (const enlace of screen.getAllByRole("link")) {
      expect(enlace.getAttribute("target")).toBe("_blank");
      expect(enlace.getAttribute("rel")).toContain("noopener");
    }
  });
});
