/**
 * @vitest-environment jsdom
 *
 * PAN-ONB-01 — the behaviour the annotations prescribe, checked as a user meets it.
 *
 * The assertions use the exact copy from
 * `docs/aidlc/inputs/prototipos/anotaciones-comportamiento.html`. If somebody reworks a
 * message, this fails and the change becomes a decision instead of a drift.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const empujar = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: empujar }) }));

const registrar = vi.fn();
const ingresar = vi.fn();
vi.mock("@/features/identity/api/cliente", async () => {
  const real = await vi.importActual<typeof import("@/features/identity/api/cliente")>(
    "@/features/identity/api/cliente",
  );
  return { ...real, registrar: () => registrar(), ingresar: () => ingresar() };
});

const { FormularioDeIngreso } = await import("@/features/identity/components/FormularioDeIngreso");
const { ErrorDeFormulario } = await import("@/features/identity/api/cliente");

afterEach(() => {
  cleanup();
  empujar.mockReset();
  registrar.mockReset();
  ingresar.mockReset();
});

function escribir(etiqueta: RegExp, valor: string): void {
  fireEvent.change(screen.getByLabelText(etiqueta), { target: { value: valor } });
}

function irARegistro(): void {
  fireEvent.click(screen.getByRole("button", { name: "Registrate" }));
}

describe("PAN-ONB-01 — ingreso", () => {
  it("arranca en modo ingresar, sin pedir términos", () => {
    render(<FormularioDeIngreso />);

    expect(screen.getByRole("button", { name: "Ingresar" })).toBeDefined();
    expect(screen.queryByLabelText(/Términos/)).toBeNull();
  });

  it("una contraseña corta muestra el mensaje de RN-01 y no llama a la API", () => {
    render(<FormularioDeIngreso />);
    escribir(/Email/, "ana@empresa.com");
    escribir(/Contraseña/, "corta");

    fireEvent.click(screen.getByRole("button", { name: "Ingresar" }));

    expect(screen.getByText("La contraseña debe tener al menos 8 caracteres.")).toBeDefined();
    expect(ingresar).not.toHaveBeenCalled();
  });

  it("credenciales correctas llevan al paso pendiente del onboarding", async () => {
    ingresar.mockResolvedValue({ onboarding_completo: false });
    render(<FormularioDeIngreso />);
    escribir(/Email/, "ana@empresa.com");
    escribir(/Contraseña/, "una-contrasena");

    fireEvent.click(screen.getByRole("button", { name: "Ingresar" }));

    await waitFor(() => expect(empujar).toHaveBeenCalledWith("/onboarding/empresa"));
  });

  it("con el onboarding completo va al panel", async () => {
    ingresar.mockResolvedValue({ onboarding_completo: true });
    render(<FormularioDeIngreso />);
    escribir(/Email/, "ana@empresa.com");
    escribir(/Contraseña/, "una-contrasena");

    fireEvent.click(screen.getByRole("button", { name: "Ingresar" }));

    await waitFor(() => expect(empujar).toHaveBeenCalledWith("/panel"));
  });

  it("un error de credenciales se muestra sin decir cuál de los dos falló", async () => {
    ingresar.mockRejectedValue(new ErrorDeFormulario("Email o contraseña incorrectos."));
    render(<FormularioDeIngreso />);
    escribir(/Email/, "ana@empresa.com");
    escribir(/Contraseña/, "una-contrasena");

    fireEvent.click(screen.getByRole("button", { name: "Ingresar" }));

    await waitFor(() => expect(screen.getByText("Email o contraseña incorrectos.")).toBeDefined());
  });
});

describe("PAN-ONB-01 — registro", () => {
  it("al registrarse aparecen el nombre y los términos", () => {
    render(<FormularioDeIngreso />);

    irARegistro();

    expect(screen.getByLabelText(/Tu nombre/)).toBeDefined();
    expect(screen.getByLabelText(/Acepto los/)).toBeDefined();
  });

  it("sin aceptar los términos no se registra (HU-E1-03 RN-02)", () => {
    render(<FormularioDeIngreso />);
    irARegistro();
    escribir(/Email/, "ana@empresa.com");
    escribir(/Contraseña/, "una-contrasena");
    escribir(/Tu nombre/, "Ana");

    fireEvent.click(screen.getByRole("button", { name: "Crear cuenta" }));

    expect(screen.getByText("Debés aceptar los Términos y Condiciones.")).toBeDefined();
    expect(registrar).not.toHaveBeenCalled();
  });

  it("aceptando los términos sí se registra y avanza al paso 2", async () => {
    registrar.mockResolvedValue({ onboarding_completo: false });
    render(<FormularioDeIngreso />);
    irARegistro();
    escribir(/Email/, "ana@empresa.com");
    escribir(/Contraseña/, "una-contrasena");
    escribir(/Tu nombre/, "Ana");
    fireEvent.click(screen.getByLabelText(/Acepto los/));

    fireEvent.click(screen.getByRole("button", { name: "Crear cuenta" }));

    await waitFor(() => expect(empujar).toHaveBeenCalledWith("/onboarding/empresa"));
  });

  it("un email ya registrado ofrece iniciar sesión, como pide RN-03", async () => {
    registrar.mockRejectedValue(
      new ErrorDeFormulario("Ese email ya tiene una cuenta. ¿Iniciar sesión?"),
    );
    render(<FormularioDeIngreso />);
    irARegistro();
    escribir(/Email/, "ana@empresa.com");
    escribir(/Contraseña/, "una-contrasena");
    escribir(/Tu nombre/, "Ana");
    fireEvent.click(screen.getByLabelText(/Acepto los/));

    fireEvent.click(screen.getByRole("button", { name: "Crear cuenta" }));

    await waitFor(() =>
      expect(screen.getByText("Ese email ya tiene una cuenta. ¿Iniciar sesión?")).toBeDefined(),
    );
  });

  it("volver a ingresar limpia los errores del otro modo", () => {
    render(<FormularioDeIngreso />);
    irARegistro();
    escribir(/Contraseña/, "corta");
    fireEvent.click(screen.getByRole("button", { name: "Crear cuenta" }));
    expect(screen.getByText("La contraseña debe tener al menos 8 caracteres.")).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: "Ya tengo cuenta" }));

    expect(screen.queryByText("La contraseña debe tener al menos 8 caracteres.")).toBeNull();
  });

  it("ofrece Google y recuperación de contraseña", () => {
    render(<FormularioDeIngreso />);

    expect(screen.getByText("Continuar con Google")).toBeDefined();
    expect(screen.getByText("¿Olvidaste tu contraseña?")).toBeDefined();
  });
});
