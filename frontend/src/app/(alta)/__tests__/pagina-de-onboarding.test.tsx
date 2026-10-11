/**
 * @vitest-environment jsdom
 *
 * `/onboarding/empresa` (HU-E1-03 RN-03, HU-E1-08 RN-05): somebody who left the onboarding half
 * done before a new version took effect accepts first and completes afterwards.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const haySesion = vi.hoisted(() => vi.fn());
const llamarApi = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  redirect: (destino: string) => {
    throw new Error(`REDIRECT:${destino}`);
  },
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }),
}));

vi.mock("@/lib/session", () => ({ haySesion }));

vi.mock("@/lib/api", async () => {
  const real = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...real, llamarApi };
});

import { ErrorDeApi } from "@/lib/api";

import DatosDeEmpresa from "../onboarding/empresa/page";

beforeEach(() => {
  haySesion.mockReturnValue(true);
});

afterEach(() => {
  cleanup();
  haySesion.mockReset();
  llamarApi.mockReset();
});

describe("página de datos de empresa", () => {
  it("con un documento pendiente manda a aceptarlo antes de pedir los datos", async () => {
    llamarApi.mockResolvedValue({ aceptaciones_pendientes: ["PRIVACIDAD"] });

    await expect(DatosDeEmpresa()).rejects.toThrow("REDIRECT:/aceptacion-legal");
  });

  it("sin nada pendiente muestra el formulario", async () => {
    llamarApi.mockResolvedValue({ aceptaciones_pendientes: [] });

    render(await DatosDeEmpresa());

    expect(screen.getByRole("heading", { level: 1 })).toBeDefined();
  });

  it("si la API todavía no manda el campo, lo lee como nada pendiente", async () => {
    llamarApi.mockResolvedValue({});

    render(await DatosDeEmpresa());

    expect(screen.getByRole("heading", { level: 1 })).toBeDefined();
  });

  it("si la API no responde, muestra el formulario como siempre", async () => {
    llamarApi.mockRejectedValue(new ErrorDeApi(503, "caida", "ServicioNoDisponible"));

    render(await DatosDeEmpresa());

    expect(screen.getByRole("heading", { level: 1 })).toBeDefined();
  });

  it("sin sesión no consulta la API", async () => {
    haySesion.mockReturnValue(false);

    render(await DatosDeEmpresa());

    expect(llamarApi).not.toHaveBeenCalled();
  });
});
