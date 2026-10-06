/**
 * @vitest-environment jsdom
 *
 * Las secciones de la pantalla de ingesta se pueden esconder. Escondido no es borrado: el
 * contenido sigue en el DOM (un arrastre o un estado local no se pierden), y lo que cambia es lo
 * que el teclado y el lector de pantalla pueden alcanzar.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SeccionPlegable } from "../SeccionPlegable";

afterEach(cleanup);

function montar(abiertaAlInicio?: boolean): void {
  render(
    <SeccionPlegable
      titulo="Planillas vinculadas"
      subtitulo="Las fuentes desde las que entran tus datos"
      icono="planilla"
      cantidad={3}
      {...(abiertaAlInicio === undefined ? {} : { abiertaAlInicio })}
    >
      <p>contenido de la sección</p>
    </SeccionPlegable>,
  );
}

const boton = (): HTMLElement => screen.getByRole("button", { name: /Planillas vinculadas/ });

describe("SeccionPlegable", () => {
  it("arranca abierta y muestra título, subtítulo y contador", () => {
    montar();

    expect(boton().getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("Las fuentes desde las que entran tus datos")).not.toBeNull();
    expect(screen.getByLabelText("3 en total").textContent).toBe("3");
  });

  it("un clic la esconde y otro la vuelve a abrir", () => {
    montar();

    fireEvent.click(boton());
    expect(boton().getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(boton());
    expect(boton().getAttribute("aria-expanded")).toBe("true");
  });

  it("escondida, el contenido sigue en el DOM", () => {
    montar();

    fireEvent.click(boton());

    // No se desmonta: un arrastre en curso o un estado local no se pierden al plegar.
    expect(screen.getByText("contenido de la sección")).not.toBeNull();
    expect(document.querySelector('[data-abierta="false"]')).not.toBeNull();
  });

  it("puede arrancar cerrada", () => {
    montar(false);

    expect(boton().getAttribute("aria-expanded")).toBe("false");
  });

  it("el botón apunta al panel que controla", () => {
    montar();

    const panel = document.getElementById(boton().getAttribute("aria-controls") ?? "");

    expect(panel?.getAttribute("role")).toBe("region");
    expect(panel?.textContent).toContain("contenido de la sección");
  });
});
