/**
 * @vitest-environment jsdom
 */

import { act, cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Desplegable } from "@/shared";

afterEach(cleanup);

function botones(contenedor: HTMLElement): HTMLButtonElement[] {
  return Array.from(contenedor.querySelectorAll<HTMLButtonElement>("button.desplegable__boton"));
}

function boton(contenedor: HTMLElement, indice = 0): HTMLButtonElement {
  const encontrado = botones(contenedor)[indice];
  if (encontrado === undefined) throw new Error("falta el botón");
  return encontrado;
}

function clic(boton: HTMLElement): void {
  act(() => {
    boton.click();
  });
}

describe("Desplegable", () => {
  it("arranca cerrado y enlaza el botón con su región", () => {
    const { container } = render(<Desplegable titulo="Detalle">Contenido</Desplegable>);
    const encabezado = boton(container);
    expect(encabezado.getAttribute("aria-expanded")).toBe("false");
    const panel = container.querySelector("[role=region]");
    expect(encabezado.getAttribute("aria-controls")).toBe(panel?.id);
    expect(panel?.getAttribute("aria-labelledby")).toBe(encabezado.id);
  });

  it("alterna con el clic y marca el contenedor como abierto", () => {
    const { container } = render(<Desplegable titulo="Detalle">Contenido</Desplegable>);
    const encabezado = boton(container);
    clic(encabezado);
    expect(encabezado.getAttribute("aria-expanded")).toBe("true");
    expect(container.querySelector(".desplegable--abierto")).not.toBeNull();
    clic(encabezado);
    expect(encabezado.getAttribute("aria-expanded")).toBe("false");
  });

  it("respeta abiertoAlInicio, la variante simple y el resumen", () => {
    const { container } = render(
      <Desplegable titulo="Detalle" abiertoAlInicio variante="simple" resumen="3">
        Contenido
      </Desplegable>,
    );
    expect(boton(container).getAttribute("aria-expanded")).toBe("true");
    expect(container.querySelector(".desplegable--simple")).not.toBeNull();
    expect(container.querySelector(".desplegable__resumen")?.textContent).toBe("3");
  });

  it("el contenido sigue en el DOM aunque esté cerrado", () => {
    const { container } = render(<Desplegable titulo="Detalle">Texto largo</Desplegable>);
    expect(container.textContent).toContain("Texto largo");
  });

  it("en un grupo, abrir uno cierra el otro", () => {
    const { container } = render(
      <Desplegable.Grupo abiertoAlInicio="a">
        <Desplegable titulo="A" valor="a">
          uno
        </Desplegable>
        <Desplegable titulo="B" valor="b">
          dos
        </Desplegable>
      </Desplegable.Grupo>,
    );
    const a = boton(container, 0);
    const b = boton(container, 1);
    expect(a.getAttribute("aria-expanded")).toBe("true");
    expect(b.getAttribute("aria-expanded")).toBe("false");
    clic(b);
    expect(a.getAttribute("aria-expanded")).toBe("false");
    expect(b.getAttribute("aria-expanded")).toBe("true");
    clic(b);
    expect(b.getAttribute("aria-expanded")).toBe("false");
  });
});
