/**
 * @vitest-environment jsdom
 *
 * PAN-ONB-02 (HU-E1-02).
 *
 * The rule the specification is most explicit about — «"Continuar" permanece
 * deshabilitado mientras el CUIT no sea válido» — is the first thing checked, and the
 * two documented deviations (no ARCA autocomplete, two extra mandatory fields) are
 * checked too, so that reverting them is a visible failure and not a silent regression.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const empujar = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: empujar }) }));

const guardar = vi.fn();
vi.mock("@/features/identity/api/cliente", async () => {
  const real = await vi.importActual<typeof import("@/features/identity/api/cliente")>(
    "@/features/identity/api/cliente",
  );
  return { ...real, guardarEmpresa: (datos: unknown) => guardar(datos) };
});

const { FormularioDeEmpresa } = await import("@/features/identity/components/FormularioDeEmpresa");
const { ErrorDeFormulario } = await import("@/features/identity/api/cliente");

const CUIT_VALIDO = "30-71234567-1";

afterEach(() => {
  cleanup();
  empujar.mockReset();
  guardar.mockReset();
});

function escribir(etiqueta: RegExp, valor: string): void {
  fireEvent.change(screen.getByLabelText(etiqueta), { target: { value: valor } });
}

function completarTodo(cuit = CUIT_VALIDO): void {
  escribir(/CUIT/, cuit);
  escribir(/Razón social/, "Panadería Doña Rosa SRL");
  escribir(/Nombre del responsable/, "Rosa Giménez");
  escribir(/Email de contacto/, "rosa@panaderia.com");
}

function botonContinuar(): HTMLButtonElement {
  return screen.getByRole("button", { name: "Continuar" }) as HTMLButtonElement;
}

describe("PAN-ONB-02", () => {
  it("Continuar arranca deshabilitado", () => {
    render(<FormularioDeEmpresa />);

    expect(botonContinuar().disabled).toBe(true);
  });

  it("sigue deshabilitado con un CUIT de dígito verificador inválido", () => {
    render(<FormularioDeEmpresa />);

    completarTodo("30712345670");

    expect(botonContinuar().disabled).toBe(true);
    expect(
      screen.getByText("El CUIT no supera la validación del dígito verificador."),
    ).toBeDefined();
  });

  it("pide los once dígitos cuando faltan", () => {
    render(<FormularioDeEmpresa />);

    escribir(/CUIT/, "3071234");

    expect(screen.getByText("Ingresá los 11 dígitos del CUIT.")).toBeDefined();
  });

  it("se habilita solo con todos los campos obligatorios de RN-03", () => {
    render(<FormularioDeEmpresa />);
    escribir(/CUIT/, CUIT_VALIDO);
    escribir(/Razón social/, "Panadería");
    expect(botonContinuar().disabled).toBe(true);

    escribir(/Nombre del responsable/, "Rosa");
    escribir(/Email de contacto/, "rosa@panaderia.com");

    expect(botonContinuar().disabled).toBe(false);
  });

  it("pide responsable y email de contacto, que el prototipo no muestra (H7)", () => {
    render(<FormularioDeEmpresa />);

    expect(screen.getByLabelText(/Nombre del responsable/)).toBeDefined();
    expect(screen.getByLabelText(/Email de contacto/)).toBeDefined();
  });

  it("no afirma haber verificado contra ARCA, porque en este épico no lo hace (D1)", () => {
    render(<FormularioDeEmpresa />);

    escribir(/CUIT/, CUIT_VALIDO);

    expect(screen.getByText(/CUIT válido/)).toBeDefined();
    expect(screen.queryByText(/datos verificados contra ARCA/)).toBeNull();
  });

  it("envía el CUIT normalizado, sin separadores", async () => {
    guardar.mockResolvedValue({ onboarding_completo: true });
    render(<FormularioDeEmpresa />);
    completarTodo();

    fireEvent.click(botonContinuar());

    await waitFor(() =>
      expect(guardar).toHaveBeenCalledWith(expect.objectContaining({ cuit: "30712345671" })),
    );
  });

  it("al guardar lleva al panel", async () => {
    guardar.mockResolvedValue({ onboarding_completo: true });
    render(<FormularioDeEmpresa />);
    completarTodo();

    fireEvent.click(botonContinuar());

    await waitFor(() => expect(empujar).toHaveBeenCalledWith("/panel"));
  });

  it("un CUIT ya registrado se muestra sin sacar al usuario del formulario", async () => {
    guardar.mockRejectedValue(
      new ErrorDeFormulario("Ese CUIT ya está registrado en otra empresa."),
    );
    render(<FormularioDeEmpresa />);
    completarTodo();

    fireEvent.click(botonContinuar());

    await waitFor(() =>
      expect(screen.getByText("Ese CUIT ya está registrado en otra empresa.")).toBeDefined(),
    );
    expect(empujar).not.toHaveBeenCalled();
  });

  it("muestra el stepper en el paso 2", () => {
    render(<FormularioDeEmpresa />);

    expect(screen.getByLabelText("Progreso del onboarding")).toBeDefined();
    expect(screen.getByText("Empresa").closest("li")?.getAttribute("aria-current")).toBe("step");
  });
});
