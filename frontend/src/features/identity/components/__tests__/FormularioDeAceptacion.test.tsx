/**
 * @vitest-environment jsdom
 *
 * Caso 43 — accepting an invitation asks for 8 characters and a confirmation.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", async () => {
  const { routerQueSuspende } = await import("@/shared/__tests__/router-que-suspende");
  return { useRouter: () => routerQueSuspende };
});

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
const { ArnesDeRouter, reiniciarRouter, resolverNavegacion, routerQueSuspende } = await import(
  "@/shared/__tests__/router-que-suspende"
);
const empujar = routerQueSuspende.push;

const TOKEN = "un-token-de-invitacion";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  reiniciarRouter();
});

function aceptarLaPolitica(): void {
  fireEvent.click(screen.getByLabelText(/Política de Privacidad/));
}

function completar(nombre: string, contrasena: string, confirmacion: string): void {
  aceptarLaPolitica();
  fireEvent.change(screen.getByLabelText("Tu nombre"), { target: { value: nombre } });
  fireEvent.change(screen.getByLabelText("Contraseña"), { target: { value: contrasena } });
  fireEvent.change(screen.getByLabelText("Repetí la contraseña"), {
    target: { value: confirmacion },
  });
}

describe("FormularioDeAceptacion — la política de privacidad (HU-E1-08 RN-04)", () => {
  it("pide solo la política, sin marcar, y no los términos", () => {
    render(<FormularioDeAceptacion token={TOKEN} versionDePrivacidad="1.0" />);

    const casilla = screen.getByLabelText(/Política de Privacidad/) as HTMLInputElement;
    expect(casilla.checked).toBe(false);
    expect(screen.queryByLabelText(/Términos y Condiciones/)).toBeNull();
  });

  it("sin marcarla no activa la cuenta y muestra su mensaje", () => {
    render(<FormularioDeAceptacion token={TOKEN} versionDePrivacidad="1.0" />);
    fireEvent.change(screen.getByLabelText("Tu nombre"), { target: { value: "Beto Gomez" } });
    fireEvent.change(screen.getByLabelText("Contraseña"), {
      target: { value: "una-contrasena-larga" },
    });
    fireEvent.change(screen.getByLabelText("Repetí la contraseña"), {
      target: { value: "una-contrasena-larga" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Activar mi cuenta" }));

    expect(
      screen.getByText("Debe aceptar la política de privacidad para continuar."),
    ).toBeDefined();
    expect(aceptarInvitacion).not.toHaveBeenCalled();
  });

  it("sin los textos vigentes no deja activar y lo dice", () => {
    render(<FormularioDeAceptacion token={TOKEN} versionDePrivacidad={null} />);
    completar("Beto Gomez", "una-contrasena-larga", "una-contrasena-larga");

    fireEvent.click(screen.getByRole("button", { name: "Activar mi cuenta" }));

    expect(screen.getByText(/No pudimos cargar los textos legales/)).toBeDefined();
    expect(aceptarInvitacion).not.toHaveBeenCalled();
  });
});

describe("FormularioDeAceptacion", () => {
  it("exige el nombre", () => {
    render(<FormularioDeAceptacion token={TOKEN} versionDePrivacidad="1.0" />);
    completar("", "una-contrasena-larga", "una-contrasena-larga");

    fireEvent.click(screen.getByRole("button", { name: "Activar mi cuenta" }));

    expect(screen.getByText("Decinos cómo te llamás.")).toBeDefined();
    expect(aceptarInvitacion).not.toHaveBeenCalled();
  });

  it("exige 8 caracteres, el mismo mínimo que el alta", () => {
    render(<FormularioDeAceptacion token={TOKEN} versionDePrivacidad="1.0" />);
    completar("Beto Gomez", "corta", "corta");

    fireEvent.click(screen.getByRole("button", { name: "Activar mi cuenta" }));

    expect(screen.getByText("La contraseña debe tener al menos 8 caracteres.")).toBeDefined();
    expect(aceptarInvitacion).not.toHaveBeenCalled();
  });

  it("exige que las dos coincidan", () => {
    render(<FormularioDeAceptacion token={TOKEN} versionDePrivacidad="1.0" />);
    completar("Beto Gomez", "una-contrasena-larga", "otra-contrasena-larga");

    fireEvent.click(screen.getByRole("button", { name: "Activar mi cuenta" }));

    expect(screen.getByText("Las contraseñas no coinciden.")).toBeDefined();
    expect(aceptarInvitacion).not.toHaveBeenCalled();
  });

  it("acepta y entra al onboarding si la empresa todavía lo debe", async () => {
    aceptarInvitacion.mockResolvedValue({ onboarding_completo: false });
    render(<FormularioDeAceptacion token={TOKEN} versionDePrivacidad="1.0" />);
    completar("Beto Gomez", "una-contrasena-larga", "una-contrasena-larga");

    fireEvent.click(screen.getByRole("button", { name: "Activar mi cuenta" }));

    await waitFor(() => {
      expect(empujar).toHaveBeenCalledWith("/onboarding/empresa");
    });
    expect(aceptarInvitacion).toHaveBeenCalledWith({
      token: TOKEN,
      nombre: "Beto Gomez",
      contrasena: "una-contrasena-larga",
      version_privacidad: "1.0",
    });
  });

  it("acepta y entra al panel si ya está completo", async () => {
    aceptarInvitacion.mockResolvedValue({ onboarding_completo: true });
    render(<FormularioDeAceptacion token={TOKEN} versionDePrivacidad="1.0" />);
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
    render(<FormularioDeAceptacion token={TOKEN} versionDePrivacidad="1.0" />);
    completar("Beto Gomez", "una-contrasena-larga", "una-contrasena-larga");

    fireEvent.click(screen.getByRole("button", { name: "Activar mi cuenta" }));

    await waitFor(() => {
      expect(screen.getByText("Esta invitación no es válida o ya fue utilizada.")).toBeDefined();
    });
    expect(empujar).not.toHaveBeenCalled();
  });
});

describe("FormularioDeAceptacion, mientras la navegación tarda", () => {
  it("un segundo envío después de la respuesta y antes del destino no acepta la invitación otra vez", async () => {
    aceptarInvitacion.mockResolvedValue({ onboarding_completo: true });
    render(
      <ArnesDeRouter>
        <FormularioDeAceptacion token={TOKEN} versionDePrivacidad="1.0" />
      </ArnesDeRouter>,
    );
    completar("Beto Gomez", "una-contrasena-larga", "una-contrasena-larga");

    fireEvent.click(screen.getByRole("button", { name: "Activar mi cuenta" }));
    await waitFor(() => expect(empujar).toHaveBeenCalledWith("/panel"));

    const boton = screen.getByRole("button", { name: "Activar mi cuenta" });
    expect((boton as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(boton);
    fireEvent.submit(boton.closest("form") as HTMLFormElement);
    expect(aceptarInvitacion).toHaveBeenCalledTimes(1);

    await resolverNavegacion();
    expect(aceptarInvitacion).toHaveBeenCalledTimes(1);
  });
});
