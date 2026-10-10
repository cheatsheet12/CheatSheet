/**
 * @vitest-environment jsdom
 *
 * `/` reads the legal versions on the server and hands them to the form; a failed read must
 * not take the sign-in page down (HU-E1-08 RN-03, plan case 18 for the wiring).
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const llamarApi = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", async () => {
  const real = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...real, llamarApi };
});

import Ingreso from "../page";

const VIGENTES = {
  terminos: { version: "1.1", vigente_desde: "2026-10-10", borrador: true },
  privacidad: { version: "1.0", vigente_desde: "2026-10-10", borrador: true },
};

afterEach(() => {
  cleanup();
  llamarApi.mockReset();
});

describe("página de ingreso", () => {
  it("lee las versiones vigentes con revalidación y se las pasa al formulario", async () => {
    llamarApi.mockResolvedValue(VIGENTES);

    render(await Ingreso({ searchParams: {} }));
    fireEvent.click(screen.getByRole("button", { name: "Registrate" }));
    fireEvent.click(screen.getByLabelText(/Términos y Condiciones/));
    fireEvent.click(screen.getByLabelText(/Política de Privacidad/));

    expect(llamarApi).toHaveBeenCalledWith("/legal/vigentes", { revalidarCadaSegundos: 60 });
    expect(screen.getByRole("link", { name: /Continuar con Google/ }).getAttribute("href")).toBe(
      "/api/auth/google?terminos=1.1&privacidad=1.0",
    );
  });

  it("si no puede leerlas igual muestra el ingreso", async () => {
    llamarApi.mockRejectedValue(new Error("connect ECONNREFUSED"));

    render(await Ingreso({ searchParams: {} }));

    expect(screen.getByRole("button", { name: "Ingresar" })).toBeDefined();
  });

  it("el motivo que deja el BFF abre el registro con el mensaje", async () => {
    llamarApi.mockResolvedValue(VIGENTES);

    render(await Ingreso({ searchParams: { error: "ConsentimientoRequerido" } }));

    expect(screen.getByRole("button", { name: "Crear cuenta" })).toBeDefined();
    expect(
      screen.getByText("Debe aceptar la política de privacidad para continuar."),
    ).toBeDefined();
  });
});
