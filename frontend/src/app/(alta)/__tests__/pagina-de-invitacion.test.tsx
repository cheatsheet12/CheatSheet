/**
 * @vitest-environment jsdom
 *
 * The invitation page reads the privacy policy version in force on the server and hands it
 * to the form (HU-E1-08 RN-04).
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const llamarApi = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", async () => {
  const real = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...real, llamarApi };
});

import PaginaDeInvitacion from "../invitacion/[token]/page";

afterEach(() => {
  cleanup();
  llamarApi.mockReset();
});

describe("página de invitación", () => {
  it("pide solo la política de privacidad", async () => {
    llamarApi.mockResolvedValue({
      terminos: { version: "1.1", vigente_desde: "2026-10-10", borrador: true },
      privacidad: { version: "1.0", vigente_desde: "2026-10-10", borrador: true },
    });

    render(await PaginaDeInvitacion({ params: { token: "t" } }));

    expect(screen.getByLabelText(/Política de Privacidad/)).toBeDefined();
    expect(screen.queryByLabelText(/Términos y Condiciones/)).toBeNull();
  });

  it("sin poder leer los textos no deja activar la cuenta y lo dice", async () => {
    llamarApi.mockRejectedValue(new Error("connect ECONNREFUSED"));

    render(await PaginaDeInvitacion({ params: { token: "t" } }));
    fireEvent.change(screen.getByLabelText("Tu nombre"), { target: { value: "Beto Gomez" } });
    fireEvent.change(screen.getByLabelText("Contraseña"), {
      target: { value: "una-contrasena-larga" },
    });
    fireEvent.change(screen.getByLabelText("Repetí la contraseña"), {
      target: { value: "una-contrasena-larga" },
    });
    fireEvent.click(screen.getByLabelText(/Política de Privacidad/));
    fireEvent.click(screen.getByRole("button", { name: "Activar mi cuenta" }));

    expect(screen.getByText(/No pudimos cargar los textos legales/)).toBeDefined();
  });
});
