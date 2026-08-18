/**
 * @vitest-environment jsdom
 *
 * The three pieces this unit added to the design system.
 *
 * `Modal` renders a native `<dialog>`, and jsdom does not implement `showModal`. It is
 * stubbed rather than worked around: what is under test is that the component calls it,
 * which is exactly what installs the focus trap in a real browser.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { Modal, Select, Tabla } from "@/shared";
import type { Columna } from "@/shared";

interface Fila {
  readonly id: string;
  readonly nombre: string;
}

const COLUMNAS: readonly Columna<Fila>[] = [
  { clave: "nombre", titulo: "Nombre", celda: (fila) => fila.nombre },
  { clave: "acciones", titulo: "Acciones", alDerecha: true, celda: () => <button>Editar</button> },
];

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
    this.open = true;
  });
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
    this.open = false;
  });
});

afterEach(cleanup);

describe("Tabla", () => {
  it("dibuja una fila por elemento, con sus columnas", () => {
    render(
      <Tabla
        titulo="Usuarios"
        columnas={COLUMNAS}
        filas={[
          { id: "1", nombre: "Ana Perez" },
          { id: "2", nombre: "Beto Gomez" },
        ]}
        claveDeFila={(fila) => fila.id}
        vacia="No hay nadie."
      />,
    );

    expect(screen.getAllByRole("row")).toHaveLength(3); // header + two
    expect(screen.getByText("Ana Perez")).toBeDefined();
  });

  it("sin filas muestra el estado vacío y no una tabla en blanco", () => {
    render(
      <Tabla
        titulo="Usuarios"
        columnas={COLUMNAS}
        filas={[]}
        claveDeFila={(fila) => fila.id}
        vacia="Todavía no hay nadie más en la empresa."
      />,
    );

    expect(screen.getByText("Todavía no hay nadie más en la empresa.")).toBeDefined();
    expect(screen.queryByRole("table")).toBeNull();
  });
});

describe("Modal", () => {
  it("cerrado no renderiza nada", () => {
    render(
      <Modal abierto={false} titulo="Invitar" onCerrar={() => undefined}>
        <p>contenido</p>
      </Modal>,
    );

    expect(screen.queryByText("contenido")).toBeNull();
  });

  it("abierto llama a showModal, que es lo que atrapa el foco", () => {
    render(
      <Modal abierto titulo="Invitar" onCerrar={() => undefined}>
        <p>contenido</p>
      </Modal>,
    );

    expect(screen.getByText("contenido")).toBeDefined();
    expect(HTMLDialogElement.prototype.showModal).toHaveBeenCalled();
  });

  it("el botón de cerrar avisa al que lo abrió", () => {
    const cerrar = vi.fn();
    render(
      <Modal abierto titulo="Invitar" onCerrar={cerrar}>
        <p>contenido</p>
      </Modal>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Cerrar" }));

    expect(cerrar).toHaveBeenCalledOnce();
  });
});

describe("Select", () => {
  it("la etiqueta es un label de verdad, tocable y leíble", () => {
    render(
      <Select
        id="rol"
        etiqueta="Rol"
        opciones={[
          { valor: "OPERADOR", etiqueta: "Operador" },
          { valor: "ADMINISTRADOR", etiqueta: "Administrador" },
        ]}
        value="OPERADOR"
        onChange={() => undefined}
      />,
    );

    const control = screen.getByLabelText("Rol");
    expect((control as HTMLSelectElement).value).toBe("OPERADOR");
  });

  it("con error lo anuncia y se marca inválido", () => {
    render(
      <Select
        id="rol"
        etiqueta="Rol"
        opciones={[{ valor: "OPERADOR", etiqueta: "Operador" }]}
        error="Elegí un rol."
        onChange={() => undefined}
      />,
    );

    expect(screen.getByRole("alert").textContent).toBe("Elegí un rol.");
    expect(screen.getByLabelText("Rol").getAttribute("aria-invalid")).toBe("true");
  });
});
