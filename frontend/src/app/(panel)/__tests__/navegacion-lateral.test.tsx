/**
 * @vitest-environment jsdom
 *
 * La barra lateral sabe en qué pantalla está la persona: una sola entrada queda marcada y es
 * la más específica que contiene a la ruta.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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

    // Dos veces: al montar, y otra cuando el grupo cerrado se abre para mostrar la entrada.
    expect(desplazar).toHaveBeenCalledWith({ block: "nearest" });
    const llamadas = desplazar.mock.contexts as Element[];
    expect(llamadas.at(-1)).toBe(container.querySelector(".nav__item--activo"));
  });

  it("no desplaza nada si la ruta no está en el mapa", () => {
    ruta.actual = "/otra-cosa";
    render(<NavegacionLateral />);

    expect(desplazar).not.toHaveBeenCalled();
  });
});

describe("grupos plegables", () => {
  const boton = (titulo: string): HTMLElement => screen.getByRole("button", { name: titulo });

  it("arranca con «Sistema» cerrado y el resto abierto", () => {
    ruta.actual = "/panel";
    render(<NavegacionLateral />);

    expect(boton("Sistema").getAttribute("aria-expanded")).toBe("false");
    expect(boton("Operaciones").getAttribute("aria-expanded")).toBe("true");
    expect(boton("Análisis").getAttribute("aria-expanded")).toBe("true");
  });

  it("un clic abre y otro cierra el grupo", () => {
    ruta.actual = "/panel";
    render(<NavegacionLateral />);

    fireEvent.click(boton("Sistema"));
    expect(boton("Sistema").getAttribute("aria-expanded")).toBe("true");

    fireEvent.click(boton("Sistema"));
    expect(boton("Sistema").getAttribute("aria-expanded")).toBe("false");
  });

  it("el botón apunta a la lista que controla", () => {
    ruta.actual = "/panel";
    const { container } = render(<NavegacionLateral />);

    const lista = container.querySelector(`#${boton("Operaciones").getAttribute("aria-controls")}`);
    expect(lista?.getAttribute("data-abierto")).toBe("true");
  });

  it("abre el grupo cerrado cuando la pantalla actual es una de sus entradas", () => {
    ruta.actual = "/configuracion/respuestas";
    render(<NavegacionLateral />);

    expect(boton("Sistema").getAttribute("aria-expanded")).toBe("true");
  });

  it("cerrar un grupo no le quita al resto su estado", () => {
    ruta.actual = "/panel";
    render(<NavegacionLateral />);

    fireEvent.click(boton("Operaciones"));

    expect(boton("Operaciones").getAttribute("aria-expanded")).toBe("false");
    expect(boton("Análisis").getAttribute("aria-expanded")).toBe("true");
  });
});
