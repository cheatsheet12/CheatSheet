/**
 * @vitest-environment jsdom
 *
 * El selector de fecha propio: el contrato es el de un campo de fecha (`YYYY-MM-DD` o `""`),
 * y las fechas se manejan por componentes para que el huso del navegador no corra un día.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SelectorDeFecha } from "../SelectorDeFecha";

// «Hoy» fijo: martes 6 de octubre de 2026, a mediodía (lejos de cualquier cambio de día).
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 9, 6, 12, 0, 0));
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function montar(
  props: Partial<Parameters<typeof SelectorDeFecha>[0]> = {},
): ReturnType<typeof vi.fn> {
  const alCambiar = vi.fn();
  render(
    <SelectorDeFecha id="f" etiqueta="Desde" value="2026-10-31" alCambiar={alCambiar} {...props} />,
  );
  return alCambiar;
}

const boton = (): HTMLElement => screen.getByRole("button", { name: "Desde" });
const abrir = (): void => {
  fireEvent.click(boton());
};
const dia = (nombre: string): HTMLElement => screen.getByRole("button", { name: nombre });

describe("SelectorDeFecha", () => {
  it("muestra la fecha como dd/mm/aaaa y un marcador si no hay", () => {
    montar();
    expect(boton().textContent).toBe("31/10/2026");
    cleanup();

    montar({ value: "" });
    expect(boton().textContent).toBe("dd/mm/aaaa");
  });

  it("abre el calendario del mes de la fecha elegida", () => {
    montar();
    abrir();

    expect(screen.getByRole("dialog", { name: "Elegir desde" })).not.toBeNull();
    expect(screen.getByText("Octubre de 2026")).not.toBeNull();
    expect(boton().getAttribute("aria-expanded")).toBe("true");
  });

  it("elegir un día avisa con YYYY-MM-DD y cierra", () => {
    const alCambiar = montar();
    abrir();

    fireEvent.click(dia("15 de octubre de 2026"));

    expect(alCambiar).toHaveBeenCalledWith("2026-10-15");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("marca la fecha elegida y el día de hoy", () => {
    montar();
    abrir();

    expect(dia("31 de octubre de 2026").getAttribute("aria-pressed")).toBe("true");
    expect(dia("6 de octubre de 2026").getAttribute("aria-current")).toBe("date");
  });

  it("cambia de mes con las flechas y completa la grilla con seis semanas", () => {
    montar();
    abrir();

    fireEvent.click(screen.getByRole("button", { name: "Mes siguiente" }));

    expect(screen.getByText("Noviembre de 2026")).not.toBeNull();
    expect(screen.getAllByRole("group")[0]?.querySelectorAll("button")).toHaveLength(42);
  });

  it("no corre el día al pasar de un mes largo a uno corto", () => {
    const alCambiar = montar();
    abrir();

    // Del 31 de octubre a noviembre: el 31 no existe, el foco cae en el 30.
    fireEvent.click(screen.getByRole("button", { name: "Mes siguiente" }));
    fireEvent.click(dia("30 de noviembre de 2026"));

    expect(alCambiar).toHaveBeenCalledWith("2026-11-30");
  });

  it("«Hoy» elige hoy y «Borrar» limpia el valor", () => {
    const alCambiar = montar();
    abrir();
    fireEvent.click(screen.getByRole("button", { name: "Hoy" }));
    expect(alCambiar).toHaveBeenLastCalledWith("2026-10-06");

    abrir();
    fireEvent.click(screen.getByRole("button", { name: "Borrar" }));
    expect(alCambiar).toHaveBeenLastCalledWith("");
  });

  it("deshabilita los días fuera de min y max", () => {
    const alCambiar = montar({ min: "2026-10-10", max: "2026-10-20" });
    abrir();

    expect((dia("9 de octubre de 2026") as HTMLButtonElement).disabled).toBe(true);
    expect((dia("21 de octubre de 2026") as HTMLButtonElement).disabled).toBe(true);
    expect((dia("15 de octubre de 2026") as HTMLButtonElement).disabled).toBe(false);

    fireEvent.click(dia("9 de octubre de 2026"));
    expect(alCambiar).not.toHaveBeenCalled();
  });

  it("«Hoy» queda deshabilitado si hoy está fuera del rango", () => {
    montar({ min: "2026-10-10" });
    abrir();

    expect((screen.getByRole("button", { name: "Hoy" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("las flechas mueven el foco entre días y Escape cierra devolviendo el foco", () => {
    montar();
    abrir();
    const panel = screen.getByRole("dialog");

    fireEvent.keyDown(panel, { key: "ArrowLeft" });
    expect(document.activeElement?.getAttribute("data-iso")).toBe("2026-10-30");

    fireEvent.keyDown(panel, { key: "ArrowDown" });
    expect(document.activeElement?.getAttribute("data-iso")).toBe("2026-11-06");

    fireEvent.keyDown(panel, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(boton());
  });

  it("RePág y AvPág cambian de mes, y con Mayús de año", () => {
    montar({ value: "2026-10-15" });
    abrir();
    const panel = screen.getByRole("dialog");

    fireEvent.keyDown(panel, { key: "PageDown" });
    expect(document.activeElement?.getAttribute("data-iso")).toBe("2026-11-15");

    fireEvent.keyDown(panel, { key: "PageUp", shiftKey: true });
    expect(document.activeElement?.getAttribute("data-iso")).toBe("2025-11-15");
  });

  it("un clic afuera cierra el calendario", () => {
    montar();
    abrir();

    fireEvent.mouseDown(document.body);

    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("ignora un valor que no es una fecha real", () => {
    montar({ value: "2026-02-31" });
    expect(boton().textContent).toBe("dd/mm/aaaa");
  });

  it("muestra el error y lo asocia al botón", () => {
    montar({ error: "Elegí una fecha" });

    expect(screen.getByRole("alert").textContent).toBe("Elegí una fecha");
    expect(boton().getAttribute("aria-describedby")).toBe("f-error");
  });
});
