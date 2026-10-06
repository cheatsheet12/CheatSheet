/**
 * @vitest-environment jsdom
 *
 * La barra lateral sabe en qué pantalla está la persona: una sola entrada queda marcada y es
 * la más específica que contiene a la ruta.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const ruta = vi.hoisted(() => ({ actual: "/" }));
vi.mock("next/navigation", () => ({ usePathname: () => ruta.actual }));

import { NAVEGACION, NavegacionLateral, hrefActivo } from "../navegacion-lateral";

// jsdom no implementa `scrollIntoView`: se simula para poder comprobar que se pide.
const desplazar = vi.fn();

beforeEach(() => {
  desplazar.mockClear();
  Element.prototype.scrollIntoView = desplazar;
});

afterEach(cleanup);

const HREFS = NAVEGACION.flatMap((grupo) => grupo.entradas.map((entrada) => entrada.href));

describe("hrefActivo", () => {
  it("marca la entrada cuya ruta coincide exactamente", () => {
    expect(hrefActivo("/cobros", HREFS)).toBe("/cobros");
  });

  it("marca la entrada que contiene a una pantalla más profunda", () => {
    expect(hrefActivo("/facturacion/nueva", HREFS)).toBe("/facturacion");
    expect(hrefActivo("/ingesta/mapeo/abc-123", HREFS)).toBe("/ingesta");
  });

  it("gana la entrada más específica, no la primera que empieza igual", () => {
    expect(hrefActivo("/facturacion/puntos-de-venta", HREFS)).toBe("/facturacion/puntos-de-venta");
    expect(hrefActivo("/agenda/recursos", HREFS)).toBe("/agenda/recursos");
  });

  it("compara por segmento: /agendamiento no es /agenda", () => {
    expect(hrefActivo("/agendamiento", HREFS)).toBeNull();
  });

  it("no marca nada en una ruta que no está en el mapa", () => {
    expect(hrefActivo("/ruta-inexistente", HREFS)).toBeNull();
  });
});

describe("NavegacionLateral", () => {
  it("marca una sola entrada como la página actual", () => {
    ruta.actual = "/facturacion/puntos-de-venta";
    render(<NavegacionLateral />);

    const actuales = screen
      .getAllByRole("link")
      .filter((enlace) => enlace.getAttribute("aria-current") === "page");

    expect(actuales).toHaveLength(1);
    expect(actuales[0]?.textContent).toBe("Puntos de venta");
  });

  it("no marca ninguna si la ruta no está en el mapa", () => {
    ruta.actual = "/otra-cosa";
    render(<NavegacionLateral />);

    const actuales = screen
      .getAllByRole("link")
      .filter((enlace) => enlace.getAttribute("aria-current") === "page");
    expect(actuales).toHaveLength(0);
  });

  it("declara un icono por entrada y todos quedan ocultos a los lectores de pantalla", () => {
    ruta.actual = "/panel";
    const { container } = render(<NavegacionLateral />);

    const iconos = container.querySelectorAll("svg.nav__icono");
    expect(iconos).toHaveLength(HREFS.length);
    iconos.forEach((icono) => expect(icono.getAttribute("aria-hidden")).toBe("true"));
  });

  it("lleva la entrada activa a la vista, y sólo la activa", () => {
    ruta.actual = "/configuracion/respuestas";
    const { container } = render(<NavegacionLateral />);

    expect(desplazar).toHaveBeenCalledTimes(1);
    expect(desplazar).toHaveBeenCalledWith({ block: "nearest" });
    const [llamada] = desplazar.mock.contexts as Element[];
    expect(llamada).toBe(container.querySelector(".nav__item--activo"));
  });

  it("no desplaza nada si la ruta no está en el mapa", () => {
    ruta.actual = "/otra-cosa";
    render(<NavegacionLateral />);

    expect(desplazar).not.toHaveBeenCalled();
  });
});
