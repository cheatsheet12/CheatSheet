/**
 * @vitest-environment jsdom
 *
 * Caso 43 — accepting an invitation asks for 8 characters and a confirmation.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const empujar = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: empujar }) }));

const aceptarInvitacion = vi.fn();
vi.mock("@/features/identity/api/cliente", async () => {
  const real = await vi.importActual<typeof import("@/features/identity/api/cliente")>(
    "@/features/identity/api/cliente",
  );
  return { ...real, aceptarInvitacion: (...args: unknown[]) => aceptarInvitacion(...args) };
});

const { FormularioDeAceptacion } = await import(
  "@/features/identity/components/FormularioDeAceptacion"
);
const { ErrorDeFormulario } = await import("@/features/identity/api/cliente");

const TOKEN = "un-token-de-invitacion";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function completar(nombre: string, contrasena: string, confirmacion: string): void {
  fireEvent.change(screen.getByLabelText("Tu nombre"), { target: { value: nombre } });
  fireEvent.change(screen.getByLabelText("Contraseña"), { target: { value: contrasena } });
  fireEvent.change(screen.getByLabelText("Repetí la contraseña"), {
    target: { value: confirmacion },
  });
}

describe("FormularioDeAceptacion", () => {
  it("exige el nombre", () => {
    render(<FormularioDeAceptacion token={TOKEN} />);
    completar("", "una-contrasena-larga", "una-contrasena-larga");

    fireEvent.click(screen.getByRole("button", { name: "Activar mi cuenta" }));

    expect(screen.getByText("Decinos cómo te llamás.")).toBeDefined();
    expect(aceptarInvitacion).not.toHaveBeenCalled();
  });

  it("exige 8 caracteres, el mismo mínimo que el alta", () => {
    render(<FormularioDeAceptacion token={TOKEN} />);
    completar("Beto Gomez", "corta", "corta");

    fireEvent.click(screen.getByRole("button", { name: "Activar mi cuenta" }));

    expect(screen.getByText("La contraseña debe tener al menos 8 caracteres.")).toBeDefined();
    expect(aceptarInvitacion).not.toHaveBeenCalled();
  });

  it("exige que las dos coincidan", () => {
    render(<FormularioDeAceptacion token={TOKEN} />);
    completar("Beto Gomez", "una-contrasena-larga", "otra-contrasena-larga");

    fireEvent.click(screen.getByRole("button", { name: "Activar mi cuenta" }));

    expect(screen.getByText("Las contraseñas no coinciden.")).toBeDefined();
    expect(aceptarInvitacion).not.toHaveBeenCalled();
  });

  it("acepta y entra al onboarding si la empresa todavía lo debe", async () => {
    aceptarInvitacion.mockResolvedValue({ onboarding_completo: false });
    render(<FormularioDeAceptacion token={TOKEN} />);
    completar("Beto Gomez", "una-contrasena-larga", "una-contrasena-larga");

    fireEvent.click(screen.getByRole("button", { name: "Activar mi cuenta" }));

    await waitFor(() => {
      expect(empujar).toHaveBeenCalledWith("/onboarding/empresa");
    });
    expect(aceptarInvitacion).toHaveBeenCalledWith({
      token: TOKEN,
      nombre: "Beto Gomez",
      contrasena: "una-contrasena-larga",
    });
  });

  it("acepta y entra al panel si ya está completo", async () => {
    aceptarInvitacion.mockResolvedValue({ onboarding_completo: true });
    render(<FormularioDeAceptacion token={TOKEN} />);
    completar("Beto Gomez", "una-contrasena-larga", "una-contrasena-larga");

    fireEvent.click(screen.getByRole("button", { name: "Activar mi cuenta" }));

    await waitFor(() => {
      expect(empujar).toHaveBeenCalledWith("/panel");
    });
  });

  it("un token usado o vencido dice lo mismo y no navega", async () => {
    aceptarInvitacion.mockRejectedValue(
      new ErrorDeFormulario("Esta invitación no es válida o ya fue utilizada."),
    );
    render(<FormularioDeAceptacion token={TOKEN} />);
    completar("Beto Gomez", "una-contrasena-larga", "una-contrasena-larga");

    fireEvent.click(screen.getByRole("button", { name: "Activar mi cuenta" }));

    await waitFor(() => {
      expect(screen.getByText("Esta invitación no es válida o ya fue utilizada.")).toBeDefined();
    });
    expect(empujar).not.toHaveBeenCalled();
  });
});
