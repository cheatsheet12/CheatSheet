/**
 * @vitest-environment jsdom
 *
 * `/aceptacion-legal` (HU-E1-03 RN-03, HU-E1-08 RN-05): the server reads what is pending and
 * hands it to the form; with nothing pending there is nothing to show.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const haySesion = vi.hoisted(() => vi.fn());
const llamarApi = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  redirect: (destino: string) => {
    throw new Error(`REDIRECT:${destino}`);
  },
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

vi.mock("@/lib/session", () => ({ haySesion }));

vi.mock("@/lib/api", async () => {
  const real = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...real, llamarApi };
});

import { ErrorDeApi } from "@/lib/api";

import PaginaDeAceptacionLegal from "../aceptacion-legal/page";

const PRIVACIDAD = {
  documento: "PRIVACIDAD",
  version: "1.2",
  vigente_desde: "2026-11-01",
  borrador: false,
};

beforeEach(() => {
  haySesion.mockReturnValue(true);
});

afterEach(() => {
  cleanup();
  haySesion.mockReset();
  llamarApi.mockReset();
});

describe("página de aceptación legal", () => {
  it("muestra lo pendiente con «Aceptar» y «Cerrar sesión»", async () => {
    llamarApi.mockResolvedValue({ pendientes: [PRIVACIDAD] });

    render(await PaginaDeAceptacionLegal());

    expect(llamarApi).toHaveBeenCalledWith("/legal/pendientes");
    expect(screen.getByRole("link", { name: /Política de Privacidad/ })).toBeDefined();
    expect(screen.getByRole("button", { name: "Aceptar" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Cerrar sesión" })).toBeDefined();
  });

  it("sin nada pendiente manda al panel y no muestra una pantalla vacía", async () => {
    llamarApi.mockResolvedValue({ pendientes: [] });

    await expect(PaginaDeAceptacionLegal()).rejects.toThrow("REDIRECT:/panel");
  });

  it("sin sesión renueva y vuelve acá, sin llamar a la API", async () => {
    haySesion.mockReturnValue(false);

    await expect(PaginaDeAceptacionLegal()).rejects.toThrow(
      "REDIRECT:/api/auth/renovar?destino=/aceptacion-legal",
    );
    expect(llamarApi).not.toHaveBeenCalled();
  });

  it("si la API rechaza la sesión vuelve al ingreso", async () => {
    llamarApi.mockRejectedValue(
      new ErrorDeApi(401, "Se requiere iniciar sesion.", "NoAutenticado"),
    );

    await expect(PaginaDeAceptacionLegal()).rejects.toThrow("REDIRECT:/");
  });

  it("si la API está caída no finge que no hay nada pendiente", async () => {
    llamarApi.mockRejectedValue(new ErrorDeApi(503, "caida", "ServicioNoDisponible"));

    await expect(PaginaDeAceptacionLegal()).rejects.toThrow(ErrorDeApi);
  });
});
