/**
 * @vitest-environment jsdom
 *
 * La tarjeta «Fechas sin atención» (caso 39): agregar, quitar, no repetir, ocultar las pasadas
 * (que igual viajan) y decir que no bloquea los turnos.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FechasSinAtencion } from "../FechasSinAtencion";

const HOY = "2026-10-05";

afterEach(() => {
  cleanup();
});

function Arnes({
  inicial,
  alCambiar,
  deshabilitado = false,
}: {
  inicial: readonly string[];
  alCambiar?: (fechas: string[]) => void;
  deshabilitado?: boolean;
}): JSX.Element {
  const [fechas, setFechas] = useState<readonly string[]>(inicial);
  return (
    <FechasSinAtencion
      fechas={fechas}
      hoy={HOY}
      deshabilitado={deshabilitado}
      onCambiar={(nuevas) => {
        setFechas(nuevas);
        alCambiar?.(nuevas);
      }}
    />
  );
}

function escribir(fecha: string): void {
  fireEvent.change(screen.getByLabelText("Día sin atención"), { target: { value: fecha } });
}

describe("FechasSinAtencion", () => {
  it("agregar una fecha la suma a la tabla", () => {
    render(<Arnes inicial={[]} />);

    escribir("2026-10-12");
    fireEvent.click(screen.getByRole("button", { name: "Agregar fecha" }));

    expect(screen.getByText("2026-10-12")).toBeTruthy();
    expect((screen.getByLabelText("Día sin atención") as HTMLInputElement).value).toBe("");
  });

  it("«Quitar» la saca", () => {
    render(<Arnes inicial={["2026-10-12", "2026-10-14"]} />);

    fireEvent.click(screen.getAllByRole("button", { name: "Quitar" })[0] as HTMLElement);

    expect(screen.queryByText("2026-10-12")).toBeNull();
    expect(screen.getByText("2026-10-14")).toBeTruthy();
  });

  it("una fecha repetida no se agrega y lo dice", () => {
    const alCambiar = vi.fn();
    render(<Arnes inicial={["2026-10-12"]} alCambiar={alCambiar} />);

    escribir("2026-10-12");

    expect(screen.getByText("Esa fecha ya está cargada.")).toBeTruthy();
    const boton = screen.getByRole("button", { name: "Agregar fecha" }) as HTMLButtonElement;
    expect(boton.disabled).toBe(true);
    fireEvent.click(boton);
    expect(alCambiar).not.toHaveBeenCalled();
  });

  it("las fechas pasadas no se muestran pero viajan sin cambios", () => {
    const alCambiar = vi.fn();
    render(<Arnes inicial={["2026-09-30", "2026-10-12"]} alCambiar={alCambiar} />);

    expect(screen.queryByText("2026-09-30")).toBeNull();
    expect(screen.getByText("2026-10-12")).toBeTruthy();

    escribir("2026-10-14");
    fireEvent.click(screen.getByRole("button", { name: "Agregar fecha" }));

    expect(alCambiar).toHaveBeenLastCalledWith(["2026-09-30", "2026-10-12", "2026-10-14"]);

    fireEvent.click(screen.getAllByRole("button", { name: "Quitar" })[0] as HTMLElement);

    expect(alCambiar).toHaveBeenLastCalledWith(["2026-09-30", "2026-10-14"]);
  });

  it("no agrega una fecha anterior a hoy", () => {
    render(<Arnes inicial={[]} />);

    escribir("2026-10-01");

    expect(
      (screen.getByRole("button", { name: "Agregar fecha" }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("sin fechas muestra el texto vacío y la ayuda que dice que no bloquea los turnos", () => {
    render(<Arnes inicial={[]} />);

    expect(screen.getByText("No hay fechas sin atención cargadas.")).toBeTruthy();
    expect(screen.getByText(/No bloquea los turnos: para eso, cargá la excepción/)).toBeTruthy();
  });

  it("deshabilitada, se ve pero no se edita", () => {
    render(<Arnes inicial={["2026-10-12"]} deshabilitado />);

    expect(screen.getByText("2026-10-12")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Quitar" })).toBeNull();
    expect(screen.queryByLabelText("Día sin atención")).toBeNull();
  });
});
